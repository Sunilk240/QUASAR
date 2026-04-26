"""
Tool Execution Module

Handles the agentic loop, tool calls, and result handling.
Supports both synchronous and streaming execution.
"""

from typing import List, Dict, Any, Optional, AsyncGenerator
from pathlib import Path
import asyncio

from langchain_core.messages import AIMessage, SystemMessage

from ..types import ExecutionResult, TaskType
from ..config import AgentConfig
from ..tools import get_tools_for_task, ToolExecutor, has_tool_calls, get_tool_calls
from ..logger import (
    agent_logger,
    log_agentic_start,
    log_agentic_complete,
    log_agentic_iteration,
    log_agentic_max_iterations
)
from .verifier import Verifier, VerificationStatus, VerificationResult


class _LoopDetector:
    """Detects if the agent is stuck in a loop calling the same tools repeatedly."""
    
    def __init__(self, window_size: int = 5, threshold: int = 3):
        self.history = []
        self.window_size = window_size
        self.threshold = threshold
    
    def add_call(self, tool_name: str, tool_args: dict) -> None:
        """Add a tool call to history."""
        # Create a signature for this call (tool name + key args)
        key_args = str(sorted(tool_args.items())[:3]) if tool_args else ""
        call_signature = f"{tool_name}:{key_args}"
        
        self.history.append(call_signature)
        if len(self.history) > self.window_size:
            self.history.pop(0)
    
    def is_looping(self) -> bool:
        """Check if the same call is repeating too many times."""
        if len(self.history) < self.threshold:
            return False
        
        # Check if last N calls are identical
        recent = self.history[-self.threshold:]
        return len(set(recent)) == 1  # All identical
    
    def reset(self) -> None:
        """Reset the detector."""
        self.history = []


def _get_progress_message(tool_name: str, tool_args: dict) -> str:
    """Generate a human-readable progress message for a tool call."""
    
    # Extract common args
    path = tool_args.get('path', tool_args.get('file_path', ''))
    if path:
        # Get just the filename
        path = path.replace('\\', '/').split('/')[-1]
    
    messages = {
        # File tools
        'read_file': f"Reading `{path}`...",
        'read_file_chunk': f"Reading section of `{path}`...",
        'create_file': f"Creating `{path}`...",  
        'modify_file': f"Modifying `{path}`...",
        'patch_file': f"Patching `{path}`...",
        'delete_file': f"Deleting `{path}`...",
        'move_file': f"Moving `{path}`...",
        
        # Search tools
        'find_files': f"Finding files matching `{tool_args.get('pattern', '*')}`...",
        'search_content': f"Searching for \"{tool_args.get('query', '')}\"...",
        'explore_codebase': "Scanning project structure...",
        'list_directory': f"Listing directory `{path or '.'}`...",
        
        # Terminal tools
        'suggest_command': "Suggesting command...",
        'check_command_available': f"Checking if `{tool_args.get('command', '')}` is available...",
        'run_command': f"Running `{tool_args.get('command', '')[:50]}`...",
        
        # Web tools
        'suggest_web_search': f"Suggesting search for \"{tool_args.get('query', '')}\"...",
        'read_url_simple': f"Reading URL content...",
        
        # Code intelligence tools
        'get_diagnostics': f"Analyzing `{path}` for issues...",
        'get_symbols': f"Listing symbols in `{path}`...",
        'find_definition': f"Finding definition of `{tool_args.get('symbol', '')}`...",
        'find_references': f"Finding references to `{tool_args.get('symbol', '')}`...",
    }
    
    return messages.get(tool_name, f"Executing {tool_name}...")


def _generate_observation(tool_name: str, tool_args: dict, result: str) -> Optional[str]:
    """Generate a human-readable observation after a tool completes."""
    
    result_lower = result.lower() if result else ""
    result_start = result[:200].lower() if result else ""
    path = tool_args.get('path', tool_args.get('file_path', ''))
    if path:
        path = path.replace('\\', '/').split('/')[-1]
    
    # Handle errors/failures
    is_error = (
        result_start.startswith("error:") or
        result_start.startswith("error -") or
        "filenotfounderror" in result_start or
        "does not exist" in result_start or
        "no such file" in result_start or
        "failed:" in result_start or
        "permission denied" in result_start
    )
    
    if is_error:
        if tool_name == "read_file":
            return f"⚠️ `{path}` not found. Let me search for similar files..."
        elif tool_name == "list_directory":
            return "⚠️ Could not list directory. Checking permissions..."
        elif tool_name == "find_files":
            return "⚠️ No matching files found. Trying broader search..."
        else:
            return f"⚠️ {tool_name} encountered an issue. Adjusting approach..."
    
    # Handle successes - don't show observation for reads (too verbose)
    if tool_name == "read_file":
        return None
    
    elif tool_name in ("list_directory", "explore_codebase"):
        return "✓ Found the directory structure. Looking for relevant files..."
    
    elif tool_name == "create_file":
        return f"✓ Created `{path}` successfully."
    
    elif tool_name in ("modify_file", "patch_file"):
        return f"✓ Updated `{path}` with the changes."
    
    elif tool_name == "delete_file":
        return f"✓ Deleted `{path}`."
    
    elif tool_name == "move_file":
        return f"✓ Moved `{path}`."
    
    elif tool_name == "search_content":
        return "✓ Search completed."
    
    elif tool_name == "suggest_command":
        return "✓ Command suggested for user to run."
    
    return None


class AgenticExecutor:
    """
    Executes tools in an agentic loop.
    
    Supports both synchronous and streaming execution modes.
    """
    
    def __init__(self, model_router, config=None, context_manager=None):
        self.model_router = model_router
        self.config = config or AgentConfig
        self.context_manager = context_manager  # P10: wired session context tracking
        self.verifier = None  # Will be set when workspace is known
        self.hooks_manager = None  # Will be set when workspace is known
        agent_logger.info("🔧 AgenticExecutor initialized")
    
    def set_workspace(self, workspace: Path):
        """Set workspace and initialize verifier."""
        self.verifier = Verifier(workspace)
        agent_logger.debug(f"Verifier initialized for workspace: {workspace}")
    
    def set_hooks_manager(self, hooks_manager):
        """Set hooks manager for lifecycle hooks."""
        self.hooks_manager = hooks_manager
        agent_logger.debug("Hooks manager set for executor")
    
    async def _verify_tool_result(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        result: str
    ) -> Optional[VerificationResult]:
        """
        Verify tool result based on tool type.
        
        Args:
            tool_name: Name of the tool
            tool_args: Arguments passed to tool
            result: Result from tool execution
            
        Returns:
            VerificationResult or None if verification not applicable
        """
        if not self.verifier:
            return None
        
        # Parse result if it's a JSON string
        result_dict = {}
        if isinstance(result, str):
            try:
                import json
                result_dict = json.loads(result)
            except:
                result_dict = {"output": result}
        else:
            result_dict = result
        
        # Verify based on tool type
        if tool_name == "create_file":
            path = tool_args.get("path", "")
            if path:
                # Detect language for syntax check
                language = self._detect_language(path)
                
                # First verify file was created
                create_verification = await self.verifier.verify_file_created(path)
                if create_verification.status != VerificationStatus.PASSED:
                    return create_verification
                
                # Then verify syntax if applicable
                if language in ["python", "json", "yaml", "yml"]:
                    syntax_verification = await self.verifier.verify_syntax(path, language)
                    if syntax_verification.status == VerificationStatus.FAILED:
                        return syntax_verification
                
                return create_verification
        
        elif tool_name == "modify_file":
            path = tool_args.get("path", "")
            if path:
                language = self._detect_language(path)
                if language in ["python", "json", "yaml", "yml"]:
                    return await self.verifier.verify_syntax(path, language)
        
        elif tool_name == "run_terminal_command":
            command = tool_args.get("command", "")
            return await self.verifier.verify_command_success(command, result_dict)
        
        # No verification for other tools
        return None
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".html": "html",
            ".css": "css",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "text")
    
    async def _invoke_selected_model_only(
        self,
        model,
        messages: List,
        provider: str,
        model_name: str,
        tools=None
    ):
        """
        Invoke ONLY the user-selected model without fallback.
        
        When user explicitly selects a model (not Auto), we should:
        1. Try the selected model
        2. On rate limit: rotate credentials within same provider
        3. If all keys exhausted: raise exception (NO fallback to other providers)
        
        This matches the original backend behavior.
        
        Args:
            model: Model instance
            messages: Messages to send
            provider: Provider name
            model_name: Model name
            tools: Tools for rebinding after key rotation
            
        Returns:
            Tuple of (response, provider, model_name)
        """
        current_model = model
        max_keys = self.model_router.cred_manager.get_key_count(provider)
        keys_tried = 0
        last_error = None
        
        agent_logger.info(f"🎯 Selected model mode: {provider}/{model_name} ({max_keys} keys available)")
        
        while keys_tried < max(max_keys, 1):
            keys_tried += 1
            
            try:
                agent_logger.info(f"🔑 Attempt {keys_tried}/{max_keys} with {provider}/{model_name}")
                response = await current_model.ainvoke(messages)
                
                # Success!
                agent_logger.info(f"✅ SUCCESS: {provider}/{model_name}")
                return (response, provider, model_name)
                
            except Exception as e:
                error_msg = str(e)
                last_error = e
                
                # Check if rate limit error
                is_rate_limit = any(indicator in error_msg.lower() for indicator in [
                    "429", "rate limit", "quota", "too many requests", 
                    "tokens per day", "token_quota_exceeded"
                ])
                
                if not is_rate_limit:
                    agent_logger.error(f"❌ Non-rate-limit error: {error_msg}")
                    raise
                
                agent_logger.warning(f"⚠️ Rate limit on {provider}: {error_msg[:100]}...")
                
                # Try rotating to next key for same provider
                if self.model_router.cred_manager.rotate_credential(provider):
                    agent_logger.info(f"🔄 Rotated to next key for {provider}")
                    
                    # Get fresh model with new key
                    rotated_model = self.model_router.get_model_for_provider(
                        provider=provider,
                        model_name_or_key=model_name
                    )
                    if rotated_model:
                        current_model = rotated_model
                        if tools:
                            try:
                                current_model = current_model.bind_tools(tools)
                            except Exception as bind_err:
                                agent_logger.warning(
                                    f"⚠️ bind_tools failed after key rotation "
                                    f"({provider}): {bind_err} — continuing without tools"
                                )
                        continue  # Try again with new key
                
                # No more keys for this provider
                agent_logger.info(f"📤 No more keys for {provider}")
                break
        
        # All keys exhausted for selected provider - NO FALLBACK
        agent_logger.error(f"❌ Selected model {provider}/{model_name} exhausted all {max_keys} keys. NO FALLBACK (user-selected mode)")
        raise Exception(f"Selected model {provider}/{model_name} failed. All {max_keys} keys exhausted. (Fallback disabled for user-selected models) Last error: {str(last_error)}")
    
    async def _invoke_with_retry(
        self,
        model,
        messages: List,
        task_type: str,
        provider: str,
        model_name: str,
        tools=None,
        exhausted_providers: set = None,  # Session-level tracking of exhausted providers
        use_fallback: bool = True  # If False (user selected specific model), don't fallback
    ):
        """
        Invoke model with automatic retry on rate limits.
        
        Follows the fallback chain defined in TASK_MODELS for the given task_type.
        Skips providers that are already exhausted in this session.
        
        Flow (when use_fallback=True - Auto mode):
        1. Always start from chain[0], but SKIP exhausted providers
        2. Try current provider/model
        3. On rate limit: rotate credentials within same provider
        4. If all keys exhausted: mark provider as exhausted, move to NEXT in chain
        5. Repeat until all providers in chain exhausted
        
        Flow (when use_fallback=False - User selected model):
        1. Try ONLY the selected provider/model
        2. On rate limit: rotate credentials within same provider
        3. If all keys exhausted: raise exception (NO fallback to other providers)
        
        Args:
            model: Current model instance
            messages: Messages to send
            task_type: Task type (determines fallback chain from config)
            provider: Current provider name (for initial model)
            model_name: Current model name
            tools: Tools to rebind on fallback (optional)
            exhausted_providers: Set of providers that have exhausted all keys this session
            use_fallback: If True, fallback to other providers. If False, only use selected model.
            
        Returns:
            Tuple of (response, provider_used, model_used) - actual model that responded
            
        Raises:
            Exception: If all providers in chain are exhausted
        """
        if exhausted_providers is None:
            exhausted_providers = set()
        
        # If user selected specific model, don't use fallback chain
        if not use_fallback:
            agent_logger.info(f"🎯 User selected model: {provider}/{model_name} (fallback disabled)")
            return await self._invoke_selected_model_only(
                model=model,
                messages=messages,
                provider=provider,
                model_name=model_name,
                tools=tools
            )
        
        # Auto mode: use fallback chain
        # Get the fallback chain for THIS task type (order matters!)
        models_chain = self.config.get_models_for_task(task_type)
        agent_logger.info(f"📋 Fallback chain for '{task_type}': {[(p, k) for p, k in models_chain]}")
        
        if exhausted_providers:
            agent_logger.info(f"⏭️ Skipping exhausted providers: {exhausted_providers}")
        
        current_model = model
        current_provider = provider
        current_model_name = model_name
        last_error = None
        
        # ALWAYS start from chain[0], but skip exhausted providers
        # This is more efficient than trying exhausted providers every iteration
        for chain_index in range(len(models_chain)):
            chain_provider, chain_model_key = models_chain[chain_index]
            
            # SKIP if provider already exhausted in this session
            if chain_provider in exhausted_providers:
                agent_logger.debug(f"⏭️ Skipping {chain_provider} (exhausted in this session)")
                continue
            
            # Get provider config to resolve actual model name
            provider_config = self.config.get_provider(chain_provider)
            if provider_config and chain_model_key in provider_config.models:
                actual_model_name = provider_config.models[chain_model_key].name
            else:
                actual_model_name = chain_model_key
            
            agent_logger.info(f"🔄 Trying chain[{chain_index}]: {chain_provider}/{actual_model_name}")
            
            # Get fresh model for this provider (unless it's the initial model)
            if chain_provider != provider or chain_index > 0:
                try:
                    fresh_model = self.model_router.get_model_for_provider(
                        provider=chain_provider,
                        model_name_or_key=chain_model_key
                    )
                    if fresh_model:
                        current_model = fresh_model
                        current_provider = chain_provider
                        current_model_name = actual_model_name
                        
                        # Rebind tools if provided
                        if tools:
                            try:
                                current_model = current_model.bind_tools(tools)
                            except Exception as bind_err:
                                agent_logger.warning(f"⚠️ Tool binding failed for {chain_provider}: {bind_err}")
                        
                        agent_logger.info(f"✅ Switched to {chain_provider}/{actual_model_name}")
                    else:
                        agent_logger.warning(f"⚠️ Failed to create model for {chain_provider}, trying next...")
                        continue
                except Exception as e:
                    agent_logger.warning(f"⚠️ Error getting {chain_provider}: {e}")
                    continue
            
            # Try invoking with credential rotation within this provider
            max_keys = self.model_router.cred_manager.get_key_count(current_provider)
            keys_tried = 0
            all_keys_failed = True
            
            while keys_tried < max(max_keys, 1):
                keys_tried += 1
                
                try:
                    agent_logger.info(f"🔑 Attempt {keys_tried}/{max_keys} with {current_provider}/{current_model_name}")
                    response = await current_model.ainvoke(messages)
                    
                    # Success!
                    agent_logger.info(f"✅ SUCCESS: {current_provider}/{current_model_name}")
                    all_keys_failed = False
                    return (response, current_provider, current_model_name)
                    
                except Exception as e:
                    error_msg = str(e)
                    last_error = e
                    
                    # Check if rate limit error
                    is_rate_limit = any(indicator in error_msg.lower() for indicator in [
                        "429", "rate limit", "quota", "too many requests", 
                        "tokens per day", "token_quota_exceeded"
                    ])
                    
                    if not is_rate_limit:
                        agent_logger.error(f"❌ Non-rate-limit error: {error_msg}")
                        raise
                    
                    agent_logger.warning(f"⚠️ Rate limit on {current_provider}: {error_msg[:100]}...")
                    
                    # Try rotating to next key for same provider
                    if self.model_router.cred_manager.rotate_credential(current_provider):
                        agent_logger.info(f"🔄 Rotated to next key for {current_provider}")
                        
                        # Get fresh model with new key
                        rotated_model = self.model_router.get_model_for_provider(
                            provider=current_provider,
                            model_name_or_key=chain_model_key
                        )
                        if rotated_model:
                            current_model = rotated_model
                            if tools:
                                try:
                                    current_model = current_model.bind_tools(tools)
                                    agent_logger.info(f"✅ Tools rebound for rotated {current_provider} key")
                                except Exception as bind_err:
                                    agent_logger.error(
                                        f"❌ bind_tools FAILED on rotated {current_provider} key: {bind_err}. "
                                        "Marking provider exhausted."
                                    )
                                    exhausted_providers.add(current_provider)
                                    break  # Fall through to next provider in chain
                            continue  # Try again with new key
                    
                    # No more keys for this provider
                    agent_logger.info(f"📤 No more keys for {current_provider}")
                    break
            
            # Mark provider as exhausted if all keys failed
            if all_keys_failed:
                exhausted_providers.add(current_provider)
                agent_logger.warning(f"🚫 Provider {current_provider} marked EXHAUSTED for this session")
        
        # All providers in chain exhausted
        agent_logger.error(f"❌ All {len(models_chain)} providers in chain exhausted for task '{task_type}'")
        raise Exception(f"All providers exhausted for task '{task_type}'. Last error: {str(last_error)}")
    
    async def execute_stream(
        self,
        model,
        messages: List,
        task_type: str,
        tools: Optional[List] = None,  # Pass tools from coordinator (includes MCP)
        max_iterations: Optional[int] = None,
        use_fallback: bool = True,  # If False, don't fallback to other providers (user selected specific model)
        provider: Optional[str] = None,  # Provider name (from coordinator for user-selected model)
        model_name: Optional[str] = None  # Model name (from coordinator for user-selected model)
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Streaming version of agentic loop.
        
        Yields events for progress tracking and real-time updates.
        
        Args:
            model: LLM model with tools bound
            messages: Initial message list
            task_type: Type of task being executed
            tools: List of tools (passed from coordinator with MCP tools). If None, fetched from task_type.
            max_iterations: Maximum iterations (default from config)
            use_fallback: If True (Auto mode), use fallback chain on rate limit.
                         If False (user selected model), only try that model.
            
        Yields:
            Dict events with type and data
        """
        max_iter = max_iterations or self.config.MAX_TOOL_ITERATIONS
        
        # Use provided tools (with MCP) or fallback to native tools
        if tools is None:
            tools = get_tools_for_task(task_type)
        
        log_agentic_start(task_type, len(tools))
        
        tool_executor = ToolExecutor(tools, timeout_seconds=self.config.TOOL_TIMEOUT_SECONDS)
        loop_detector = _LoopDetector(window_size=5, threshold=3)
        
        # Session-level tracking of exhausted providers
        # Once a provider fails ALL its keys, skip it in subsequent iterations
        # This prevents wasting time retrying providers that are rate-limited for the whole day
        exhausted_providers: set = set()
        
        current_messages = list(messages)
        iteration = 0
        
        # Get model info - use passed values if provided (user-selected model), otherwise from config
        if provider and model_name:
            # User selected specific model - use their choice
            agent_logger.info(f"🎯 Using user-selected model: {provider}/{model_name}")
        else:
            # Auto mode - get from config chain
            provider = "unknown"
            model_name = "unknown"
            models_chain = self.config.get_models_for_task(task_type)
            if models_chain:
                provider, model_key = models_chain[0]
                provider_config = self.config.get_provider(provider)
                if provider_config and model_key in provider_config.models:
                    # Named model in config (e.g. ollama/glm-4.7:cloud)
                    model_name = provider_config.models[model_key].name
                else:
                    # custom_N providers: model_key IS already the real model name
                    # (get_models_for_task already resolved __env__ → CUSTOM_N_MODEL)
                    model_name = model_key
        
        # ─────────────────────────────────────────────────────────────────────
        # P7: Pre-task planning for complex queries
        # Only runs for file/code tasks with a query > 80 chars.
        # Produces a numbered plan that is injected as a SystemMessage so the
        # model knows what it's about to do before the first tool call.
        # ─────────────────────────────────────────────────────────────────────
        _planning_task_types = {"file_operations", "execution", "code_intelligence"}
        _last_human = next(
            (m for m in reversed(current_messages) if getattr(m, "type", "") == "human"),
            None,
        )
        _query_len = len(getattr(_last_human, "content", "")) if _last_human else 0

        if task_type in _planning_task_types and _query_len > 80:
            try:
                from langchain_core.messages import HumanMessage as _HM
                _plan_prompt = (
                    "You are a planning assistant. Given the task below, write a concise "
                    "numbered execution plan (3-7 steps). Be specific about WHICH files to "
                    "read/modify and WHAT changes to make. No preamble, just the numbered list.\n\n"
                    f"Task: {getattr(_last_human, 'content', '')[:500]}"
                )
                _plan_response = await model.ainvoke([_HM(content=_plan_prompt)])
                _plan_text = getattr(_plan_response, "content", "").strip()

                if _plan_text:
                    agent_logger.info(f"📋 Pre-task plan generated ({len(_plan_text)} chars)")
                    from langchain_core.messages import SystemMessage as _SM
                    current_messages.append(_SM(content=(
                        f"EXECUTION PLAN (follow this order):\n{_plan_text}"
                    )))
                    yield {"type": "plan_generated", "plan": _plan_text}
            except Exception as _plan_err:
                # Planning is best-effort — never block the main loop
                agent_logger.warning(f"⚠️ Pre-task planning skipped: {_plan_err}")

        import time as _time
        _session_start = _time.monotonic()  # P12: session timer

        
        while iteration < max_iter:
            # P12: Session-level timeout check (Python 3.10-compatible)
            elapsed = _time.monotonic() - _session_start
            if elapsed > self.config.SESSION_TIMEOUT_SECONDS:
                agent_logger.error(
                    f"⏰ Session timeout: {elapsed:.0f}s elapsed, "
                    f"limit is {self.config.SESSION_TIMEOUT_SECONDS}s"
                )
                yield {
                    "type": "error",
                    "message": (
                        f"Query timed out after {int(elapsed)}s "
                        f"(limit: {self.config.SESSION_TIMEOUT_SECONDS}s). "
                        "Try a more specific request or break it into smaller steps."
                    )
                }
                return

            iteration += 1
            remaining = max_iter - iteration
            agent_logger.info(f"🔄 Streaming agentic loop iteration {iteration}/{max_iter}")
            
            # Log exhausted providers status
            if exhausted_providers:
                agent_logger.info(f"⏭️ Session exhausted providers: {exhausted_providers}")
            
            yield {"type": "iteration", "current": iteration, "max": max_iter, "remaining": remaining}
            
            # Iteration warning: when 1 iteration remains, inject summary request
            if remaining <= 1:
                agent_logger.info(f"⚠️ {remaining} iterations remaining - injecting summary reminder")
                summary_request = f"""
[SYSTEM: CRITICAL RESOURCE LIMIT]
Only {remaining} tool iteration remaining!
You MUST include a "PROGRESS SUMMARY" block in your response:
- ✅ WHAT IS DONE: (List completed steps)
- ⏳ WHAT IS PENDING: (List remaining steps)
- 📋 CONTINUATION DATA: (Briefly describe current state for next session)

You MUST provide this summary NOW as this is your LAST chance to speak.
"""
                # Check if we already added a summary request recently
                if not any("[SYSTEM: CRITICAL RESOURCE LIMIT]" in getattr(m, 'content', '') for m in current_messages[-2:]):
                    current_messages.append(SystemMessage(content=summary_request))
                
                if remaining == 1:
                    yield {"type": "iteration_warning", "remaining": remaining, "message": "LAST iteration remaining - summarizing progress"}
            
            try:
                # Collect full response with fallback support
                # Try models in chain order, skipping exhausted providers
                # If use_fallback=False (user selected model), only try that model
                response, provider, model_name = await self._invoke_with_retry(
                    model=model,
                    messages=current_messages,
                    task_type=task_type,
                    provider=provider,
                    model_name=model_name,
                    tools=tools,
                    exhausted_providers=exhausted_providers,  # Session-level tracking
                    use_fallback=use_fallback  # If False, don't fallback to other providers
                )
                
                if has_tool_calls(response):
                    tool_calls = get_tool_calls(response)
                    agent_logger.info(f"🔧 Model requested {len(tool_calls)} tool calls")
                    
                    # IMPORTANT: Extract thinking/reasoning text BEFORE tool calls
                    # The model often explains what it's doing in response.content
                    if response.content and response.content.strip():
                        thinking_text = response.content.strip()
                        
                        # Check if this looks like a plan (has numbered steps or bullet points)
                        if any(marker in thinking_text for marker in ["\n1.", "\n2.", "- ", "* "]):
                            # Try to extract plan steps
                            steps = []
                            for line in thinking_text.split("\n"):
                                line = line.strip()
                                # Match numbered lists (1., 2., etc.) or bullet points (-, *)
                                if line and (line[0].isdigit() or line.startswith(("-", "*", "•"))):
                                    # Clean up the step text
                                    step = line.lstrip("0123456789.-*• ").strip()
                                    if step:
                                        steps.append(step)
                            
                            if steps:
                                yield {"type": "plan", "steps": steps}
                            else:
                                # Not a clear plan, just show as thinking
                                yield {"type": "thinking", "content": thinking_text}
                        else:
                            # Regular thinking/explanation
                            yield {"type": "thinking", "content": thinking_text}
                    
                    current_messages.append(response)
                    
                    # Analyze tool dependencies for parallel execution
                    independent, dependent = tool_executor._analyze_tool_dependencies(tool_calls)
                    
                    # Emit parallel execution info if applicable
                    if independent and len(independent) > 1:
                        tool_names = [tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "") for tc in independent]
                        yield {"type": "message", "content": f"⚡ Executing {len(independent)} read operations in parallel: {', '.join(tool_names)}"}
                    
                    # Execute tools with progress messages and hooks
                    all_tool_calls = independent + dependent
                    
                    # PRE_TOOL_USE HOOKS: Check each tool before execution
                    if self.hooks_manager:
                        from ..hooks import HookPoint
                        
                        filtered_tool_calls = []
                        for tool_call in all_tool_calls:
                            tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                            tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                            
                            # Run PRE_TOOL_USE hooks
                            hook_result = await self.hooks_manager.run_hooks(
                                HookPoint.PRE_TOOL_USE,
                                {
                                    "tool_name": tool_name,
                                    "args": tool_args,
                                    "iteration": iteration
                                }
                            )
                            
                            if not hook_result.allow:
                                # Hook blocked this tool
                                agent_logger.info(f"🚫 Hook blocked tool: {tool_name}")
                                yield {"type": "message", "content": hook_result.message or f"🚫 Tool {tool_name} blocked by hook"}
                                continue  # Skip this tool
                            
                            if hook_result.message:
                                # Hook has a message to display
                                yield {"type": "message", "content": hook_result.message}
                            
                            # Apply modified args if any
                            if hook_result.modified_args:
                                if isinstance(tool_call, dict):
                                    tool_call["args"].update(hook_result.modified_args)
                                else:
                                    for key, value in hook_result.modified_args.items():
                                        setattr(tool_call.args, key, value)
                            
                            filtered_tool_calls.append(tool_call)
                        
                        all_tool_calls = filtered_tool_calls
                    
                    # Show progress for each tool
                    for tool_call in all_tool_calls:
                        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                        tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                        
                        # Check for loop
                        loop_detector.add_call(tool_name, tool_args)
                        if loop_detector.is_looping():
                            agent_logger.warning("⚠️ Loop detected, stopping to avoid infinite execution")
                            yield {"type": "message", "content": "⚠️ Detected repetitive actions. Stopping to avoid infinite loop."}
                            summary = tool_executor.get_execution_summary()
                            yield {
                                "type": "done",
                                "model": model_name,
                                "provider": provider,
                                "task_type": task_type,
                                "iterations": iteration,
                                "tool_calls_count": summary["total_calls"],
                                "tools_used": summary["tools_used"],
                                "loop_detected": True
                            }
                            return
                        
                        # Progress message BEFORE tool
                        progress_msg = _get_progress_message(tool_name, tool_args)
                        yield {"type": "message", "content": progress_msg}
                        
                        # Tool start
                        yield {"type": "debug", "content": f"🔧 [DEBUG] Executing tool: {tool_name} with args: {tool_args}"}
                        yield {"type": "tool_start", "tool": tool_name, "args": tool_args}
                    
                    # Execute all tools (parallel + sequential).
                    # IMPORTANT: use all_tool_calls (post-hook filtered list),
                    # NOT the original tool_calls variable — hooks that set
                    # allow=False must actually prevent execution.
                    tool_messages = await tool_executor.execute_tool_calls(all_tool_calls)

                    # ----------------------------------------------------------------
                    # P5: Confirmation gate — scan results for requires_confirmation
                    # sentinel returned by run_command for non-safe commands.
                    # Hold execution until user responds Allow/Deny in the terminal.
                    # The session timer is PAUSED during the wait.
                    # ----------------------------------------------------------------
                    import json as _json
                    from ..tools.confirmation_gate import get_confirmation_gate as _get_gate
                    from ..tools.terminal_tools import _execute_command as _exec_cmd

                    for _msg_idx, _tm in enumerate(tool_messages):
                        try:
                            _result_data = _json.loads(_tm.content)
                        except (ValueError, TypeError):
                            continue

                        if not isinstance(_result_data, dict):
                            continue
                        if not _result_data.get("requires_confirmation"):
                            continue

                        # Found a confirmation sentinel
                        _pending_cmd = _result_data.get("command", "")
                        _pending_reason = _result_data.get("reason", "")
                        _gate = _get_gate()

                        # Yield event for CLI to display
                        yield {
                            "type": "command_confirmation_required",
                            "command": _pending_cmd,
                            "reason": _pending_reason,
                        }

                        # Pause session timer while user is reading / deciding
                        _pause_start = _time.monotonic()

                        # Await gate indefinitely — no timeout, no auto-deny
                        _approved = await _gate.wait_for_decision()

                        # Resume session timer (subtract wait time from elapsed)
                        _session_start += (_time.monotonic() - _pause_start)

                        if _approved:
                            agent_logger.info(f"run_command APPROVED by user: {_pending_cmd[:60]!r}")
                            _exec_result = _exec_cmd(_pending_cmd)
                        else:
                            agent_logger.info(f"run_command DENIED by user: {_pending_cmd[:60]!r}")
                            _exec_result = {
                                "success": False,
                                "blocked": True,
                                "exit_code": -1,
                                "stdout": "",
                                "stderr": "User denied execution.",
                                "command": _pending_cmd,
                            }

                        # Replace the sentinel ToolMessage content with the real result.
                        # tool_messages is not yet in current_messages — we just mutate
                        # it in-place here so the normal append block below picks up the
                        # correct (already-confirmed) result automatically.
                        from langchain_core.messages import ToolMessage as _ToolMessage
                        tool_messages[_msg_idx] = _ToolMessage(
                            content=_json.dumps(_exec_result),
                            tool_call_id=_tm.tool_call_id,
                        )

                    # Append all tool results (confirmed ones already patched in-place above)
                    current_messages.extend(tool_messages)

                    
                    # Process results for each tool
                    for i, tool_call in enumerate(all_tool_calls):
                        tool_name = tool_call.get("name", "") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                        tool_args = tool_call.get("args", {}) if isinstance(tool_call, dict) else getattr(tool_call, "args", {})
                        
                        # Tool complete
                        result = tool_messages[i].content if i < len(tool_messages) else "completed"
                        yield {"type": "debug", "content": f"✅ [DEBUG] Tool {tool_name} returned: {str(result)[:200]}..."}
                        yield {"type": "tool_complete", "tool": tool_name, "result": result}
                        
                        # VERIFICATION: Check if tool succeeded
                        verification_result = await self._verify_tool_result(tool_name, tool_args, result)
                        if verification_result:
                            if verification_result.status == VerificationStatus.FAILED:
                                # Emit verification failure
                                yield {"type": "observation", "tool": tool_name, "observation": f"⚠️ Verification failed: {verification_result.message}"}
                                
                                # Add suggested fix to context for model to see
                                if verification_result.suggested_fix:
                                    fix_message = f"Verification failed for {tool_name}: {verification_result.message}. Suggested fix: {verification_result.suggested_fix}"
                                    current_messages.append(SystemMessage(content=fix_message))
                            elif verification_result.status == VerificationStatus.PASSED:
                                # Emit success verification (optional, can be verbose)
                                agent_logger.debug(f"Verification passed for {tool_name}")
                        
                        # Observation AFTER tool
                        observation = _generate_observation(tool_name, tool_args, result)
                        if observation:
                            yield {"type": "message", "content": observation}
                        
                        # POST_TOOL_USE HOOKS
                        if self.hooks_manager:
                            from ..hooks import HookPoint
                            
                            hook_result = await self.hooks_manager.run_hooks(
                                HookPoint.POST_TOOL_USE,
                                {
                                    "tool_name": tool_name,
                                    "args": tool_args,
                                    "result": result,
                                    "iteration": iteration
                                }
                            )
                            
                            if hook_result.message:
                                yield {"type": "message", "content": hook_result.message}
                        
                        # Track file changes in session context + notify CLI
                        file_modifying_tools = [
                            "create_file", "delete_file", "modify_file",
                            "patch_file", "move_file", "rename_file"
                        ]
                        if tool_name in file_modifying_tools:
                            # P10: Record in context manager so system prompt stays accurate
                            if self.context_manager:
                                path = tool_args.get("path", tool_args.get("file_path", ""))
                                if path:
                                    if tool_name == "create_file":
                                        self.context_manager.record_file_created(path)
                                    elif tool_name in ("modify_file", "patch_file"):
                                        self.context_manager.record_file_modified(path)
                    
                    continue
                else:
                    # No tool calls - stream the final response text
                    if response.content:
                        # Yield content in chunks for smoother streaming
                        content = response.content
                        chunk_size = 10
                        for i in range(0, len(content), chunk_size):
                            yield {"type": "token", "content": content[i:i+chunk_size]}
                    
                    summary = tool_executor.get_execution_summary()
                    log_agentic_complete(iteration, summary["tools_used"], summary["total_calls"])
                    
                    # ON_COMPLETE HOOK
                    if self.hooks_manager:
                        from ..hooks import HookPoint
                        
                        hook_result = await self.hooks_manager.run_hooks(
                            HookPoint.ON_COMPLETE,
                            {
                                "task_type": task_type,
                                "iterations": iteration,
                                "tools_used": summary["tools_used"],
                                "tool_calls_count": summary["total_calls"]
                            }
                        )
                        
                        if hook_result.message:
                            yield {"type": "message", "content": hook_result.message}
                    
                    yield {
                        "type": "done",
                        "model": model_name,
                        "provider": provider,
                        "task_type": task_type,
                        "iterations": iteration,
                        "tool_calls_count": summary["total_calls"],
                        "tools_used": summary["tools_used"]
                    }
                    return
                    
            except Exception as e:
                error_msg = str(e)
                agent_logger.error(f"❌ Error in streaming loop iteration {iteration}: {error_msg}")
                
                # Check if this is a rate limit error that should trigger fallback
                is_rate_limit = any(indicator in error_msg.lower() for indicator in [
                    "429", "rate limit", "quota", "too many requests", "tokens per day"
                ])
                
                if is_rate_limit:
                    agent_logger.warning(f"⚠️ Rate limit detected, attempting fallback...")
                    yield {"type": "message", "content": f"⚠️ Rate limit reached, trying backup provider..."}
                    
                    # This shouldn't happen as _invoke_with_retry should handle it,
                    # but if it does, we've exhausted all options
                    yield {"type": "error", "message": f"All providers exhausted: {error_msg}"}
                else:
                    yield {"type": "error", "message": error_msg}
                
                return
        
        # Max iterations reached
        log_agentic_max_iterations(max_iter, iteration)
        summary = tool_executor.get_execution_summary()
        
        yield {
            "type": "done",
            "model": model_name,
            "provider": provider,
            "task_type": task_type,
            "iterations": iteration,
            "tool_calls_count": summary["total_calls"],
            "tools_used": summary["tools_used"],
            "max_iterations_reached": True
        }
