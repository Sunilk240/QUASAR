"""
Main Orchestrator Coordinator

Thin coordination layer that delegates to specialized modules.
This replaces the monolithic orchestrator.py with a clean, modular design.
"""

from typing import Optional, AsyncGenerator, Dict, Any
from pathlib import Path

from ..types import TaskClassification, AgentResponse, TaskType
from ..models.router import ModelRouter
from ..context import ContextManager
from ..config import AgentConfig
from ..tools import get_tools_for_task, set_workspace
from ..logger import agent_logger

from .classifier import TaskClassifier
from .prompt_builder import PromptBuilder
from .executor import AgenticExecutor
from .stream_handler import StreamHandler

# MCP support
try:
    from ...mcp import MCPManager
    from ...mcp.adapter import create_mcp_tools
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    agent_logger.warning("⚠️ MCP support not available")

# Hooks support
try:
    from ..hooks import HooksManager
    HOOKS_AVAILABLE = True
except ImportError:
    HOOKS_AVAILABLE = False
    agent_logger.warning("⚠️ Hooks support not available")


class Orchestrator:
    """
    Main coordinator - kept thin, delegates to specialists.
    
    This is the public interface that replaces the old monolithic orchestrator.
    """
    
    def __init__(self, workspace_path: Optional[str] = None):
        """
        Initialize orchestrator with all sub-components.
        
        Args:
            workspace_path: Path to workspace directory
        """
        self.model_router = ModelRouter()
        self.context_manager = ContextManager()
        
        # Initialize project context if workspace provided
        self.project_context = None
        if workspace_path:
            from ..persistence import ProjectContext
            self.project_context = ProjectContext(Path(workspace_path))
            # Initialize .quasar/ directory (creates if doesn't exist)
            is_new = self.project_context.initialize()
            if is_new:
                agent_logger.info("📁 Created .quasar/ directory with templates")
        
        self.classifier = TaskClassifier(self.model_router)
        self.prompt_builder = PromptBuilder(self.context_manager, self.project_context)
        self.executor = AgenticExecutor(self.model_router, AgentConfig, self.context_manager)
        self.stream_handler = StreamHandler()
        
        # Initialize MCP manager (looks for .quasar/mcp.json in project)
        self.mcp_manager = None
        self.mcp_tools = []
        if MCP_AVAILABLE:
            self.mcp_manager = MCPManager(workspace_path=workspace_path)
            agent_logger.info("🔌 MCP manager initialized")
        
        # Initialize hooks manager
        self.hooks_manager = None
        if HOOKS_AVAILABLE and workspace_path:
            self.hooks_manager = HooksManager(Path(workspace_path))
            hook_count = self.hooks_manager.get_hook_count()
            if hook_count > 0:
                agent_logger.info(f"🪝 Loaded {hook_count} hook(s)")
        
        self.workspace = workspace_path
        
        if workspace_path:
            set_workspace(workspace_path)
            self.context_manager.set_workspace(workspace_path)
            self.executor.set_workspace(Path(workspace_path))
            if self.hooks_manager:
                self.executor.set_hooks_manager(self.hooks_manager)
        
        agent_logger.info("🚀 Orchestrator initialized (modular architecture with project context + MCP + Hooks support)")
    
    def set_workspace(self, path: str):
        """Set the workspace path and reinitialize project context."""
        self.workspace = path
        set_workspace(path)
        self.context_manager.set_workspace(path)
        self.executor.set_workspace(Path(path))
        
        # Reinitialize project context for new workspace
        from ..persistence import ProjectContext
        self.project_context = ProjectContext(Path(path))
        is_new = self.project_context.initialize()
        if is_new:
            agent_logger.info("📁 Created .quasar/ directory with templates")
        
        # Update prompt builder with new project context
        self.prompt_builder.project_context = self.project_context
        
        # Reinitialize hooks manager for new workspace
        if HOOKS_AVAILABLE:
            self.hooks_manager = HooksManager(Path(path))
            hook_count = self.hooks_manager.get_hook_count()
            if hook_count > 0:
                agent_logger.info(f"🪝 Loaded {hook_count} hook(s)")
            if self.hooks_manager:
                self.executor.set_hooks_manager(self.hooks_manager)
        
        # Reinitialize MCP manager for new workspace
        if MCP_AVAILABLE:
            self.mcp_manager = MCPManager(workspace_path=path)
            self.mcp_tools = []  # Reset - will be loaded on first query
            agent_logger.info(f"🔌 MCP manager reinitialized for workspace: {path}")
        
        agent_logger.info(f"📁 Workspace set to: {path}")
    
    async def load_mcp_servers(self) -> int:
        """
        Load and connect to MCP servers from config.
        
        Returns:
            Number of successfully connected servers
        """
        if not self.mcp_manager:
            agent_logger.warning("⚠️ MCP not available")
            return 0
        
        try:
            count = await self.mcp_manager.load_servers()
            
            if count > 0:
                # Create LangChain tools from MCP tools
                self.mcp_tools = create_mcp_tools(self.mcp_manager)
                agent_logger.info(f"✅ Loaded {len(self.mcp_tools)} MCP tools from {count} servers")
            
            return count
        except Exception as e:
            agent_logger.error(f"❌ Error loading MCP servers: {e}")
            return 0
    
    def get_tools_with_mcp(self, task_type: str) -> list:
        """
        Get tools for task including MCP tools.
        
        Args:
            task_type: Type of task
            
        Returns:
            Combined list of native and MCP tools
        """
        native_tools = get_tools_for_task(task_type)
        
        # Add MCP tools if available
        if self.mcp_tools:
            all_tools = native_tools + self.mcp_tools
            agent_logger.debug(f"🔧 Tools: {len(native_tools)} native + {len(self.mcp_tools)} MCP = {len(all_tools)} total")
            return all_tools
        
        return native_tools
    
    async def classify_task(
        self,
        query: str,
        current_file: Optional[str] = None,
        has_selection: bool = False,
        has_error: bool = False
    ) -> TaskClassification:
        """
        Classify user query into task type.
        
        Delegates to TaskClassifier.
        """
        return await self.classifier.classify(
            query=query,
            current_file=current_file,
            has_selection=has_selection,
            has_error=has_error
        )
    
    async def process_stream(
        self,
        query: str,
        current_file: Optional[str] = None,
        file_content: Optional[str] = None,
        selected_code: Optional[str] = None,
        terminal_output: Optional[str] = None,
        error_message: Optional[str] = None,
        selected_model: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process query with streaming responses.
        
        Yields SSE events for real-time progress tracking.
        
        Args:
            Same as process()
            
        Yields:
            Dict events with type and data
        """
        # Update context
        self.context_manager.set_task_context(
            current_file=current_file,
            file_content=file_content,
            selected_code=selected_code,
            error_message=error_message,
            terminal_output=terminal_output
        )
        
        # Classify task
        has_error = bool(error_message or (terminal_output and "error" in terminal_output.lower()))
        classification = await self.classify_task(
            query=query,
            current_file=current_file,
            has_selection=bool(selected_code),
            has_error=has_error
        )
        
        # Emit classification
        yield self.stream_handler.emit_classification(
            task_type=classification.task_type.value,
            confidence=classification.confidence,
            reasoning=classification.reasoning
        )
        
        # Determine if we should use tools
        use_tools = classification.task_type.value in AgentConfig.TOOL_ENABLED_TASKS
        
        # Build messages
        messages = self.prompt_builder.build_messages(
            task_type=classification.task_type,
            query=query,
            include_tools=use_tools
        )
        
        # Record user message
        self.context_manager.add_message("user", query, classification.task_type.value)
        
        # Get model
        if selected_model and selected_model != "Auto":
            provider, model_key = selected_model.split("/", 1)
            model = self.model_router.get_model_for_provider(provider, model_key)
            if model is None:
                yield self.stream_handler.emit_error(f"Could not load selected model: {selected_model}")
                return
            model_name = model_key
            provider_name = provider
        else:
            model = self.model_router.get_model(classification.task_type.value)
            if model is None:
                yield self.stream_handler.emit_error("No models available")
                return
            
            models_chain = AgentConfig.get_models_for_task(classification.task_type.value)
            if models_chain:
                provider_name, model_key = models_chain[0]
                provider_config = AgentConfig.get_provider(provider_name)
                if provider_config and model_key in provider_config.models:
                    # Named model in config (e.g. ollama/glm-4.7:cloud)
                    model_name = provider_config.models[model_key].name
                elif provider_name.startswith("custom"):
                    # Custom slot: model_key was already resolved from CUSTOM_N_MODEL
                    # by get_models_for_task, so model_key IS the real model name.
                    model_name = model_key
                else:
                    model_name = model_key
            else:
                provider_name = "unknown"
                model_name = "unknown"
        
        # Execute
        if use_tools:
            tools = self.get_tools_with_mcp(classification.task_type.value)
            try:
                model_with_tools = model.bind_tools(tools)
            except Exception as e:
                agent_logger.warning(f"⚠️ Tool binding failed: {e}")
                use_tools = False
        
        if use_tools:
            # Streaming agentic execution
            # use_fallback=False when user selected specific model (not Auto)
            use_fallback = not (selected_model and selected_model != "Auto")
            
            full_response = ""
            async for chunk in self.executor.execute_stream(
                model=model_with_tools,
                messages=messages,
                task_type=classification.task_type.value,
                tools=tools,  # Pass tools including MCP tools
                use_fallback=use_fallback,  # Disable fallback when user selected specific model
                provider=provider_name,  # Pass provider for user-selected model
                model_name=model_name  # Pass model name for user-selected model
            ):
                # Collect response tokens for context recording
                if chunk.get("type") == "token":
                    full_response += chunk.get("content", "")
                
                # Save history when done
                if chunk.get("type") == "done":
                    agent_logger.info(f"🔍 DEBUG: Saving history on done event")
                    if full_response:
                        self.context_manager.add_message("assistant", full_response, classification.task_type.value)
                    
                    # Record in project history
                    if self.project_context:
                        summary = f"{classification.task_type.value}: {chunk.get('tool_calls_count', 0)} tool calls"
                        self.project_context.add_to_history(query, summary)
                        agent_logger.info(f"✅ Saved to history: {query[:50]}...")
                    else:
                        agent_logger.warning("⚠️ project_context is None")
                
                yield chunk
        else:
            # Simple streaming without tools
            try:
                full_response = ""
                async for chunk in model.astream(messages):
                    token = chunk.content if hasattr(chunk, 'content') else str(chunk)
                    if token:
                        full_response += token
                        yield self.stream_handler.emit_token(token)
                
                # Record assistant response
                self.context_manager.add_message("assistant", full_response, classification.task_type.value)
                
                # Record in project history (P0 FIX: was missing in streaming mode)
                if self.project_context:
                    summary = f"{classification.task_type.value}: Streamed response"
                    self.project_context.add_to_history(query, summary)
                    agent_logger.info(f"✅ Saved to history: {query[:50]}...")
                
                # Emit done
                yield self.stream_handler.emit_done(
                    model=model_name,
                    provider=provider_name,
                    task_type=classification.task_type.value,
                    iterations=1,
                    tool_calls_count=0,
                    tools_used=[]
                )
            except Exception as e:
                agent_logger.error(f"❌ Simple stream error: {e}")
                yield self.stream_handler.emit_error(str(e))
