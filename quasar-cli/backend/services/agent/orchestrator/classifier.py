"""
Task Classification Module

Extracts classification logic from the monolithic orchestrator.
Uses LLM for intelligent classification with keyword-based fallback.

Simplified to 6 tool-aligned categories (Claude Code style).
"""

from typing import Optional
import json
from langchain_core.messages import HumanMessage

from ..types import TaskType, TaskClassification
from ..models.router import ModelRouter
from ..logger import agent_logger, log_model_call, log_model_response, log_classification


CLASSIFICATION_PROMPT = """You are a task classifier for an AI code editor.
Classify the user's query into one of these tool-aligned categories:

1. file_operations - Read, write, create, edit, delete files
   KEYWORDS: create file, write, modify, edit, delete, rename, update, change code
   
2. search - Find files, search content in codebase
   KEYWORDS: find, search, where is, locate, grep, look for, show me
   
3. execution - User wants to run commands (we'll suggest, not run)
   KEYWORDS: run, execute, install, pip, npm, compile, build, test command
   
4. web - Fetch URLs, search documentation
   KEYWORDS: fetch, url, http, documentation, lookup online, web search
   
5. code_intelligence - Analyze code, find references, understand structure
   KEYWORDS: explain, what does, how does, definition, references, errors, diagnostics
   
6. chat - General conversation, questions about programming
   DEFAULT: If no specific tool category matches

IMPORTANT:
- Focus on WHAT TOOLS the agent will need, not semantic task meaning
- If query involves modifying code → file_operations
- If query involves finding something → search
- If query asks about code meaning → code_intelligence
- Be concise in reasoning

User query: {query}

Context:
- Current file: {current_file}
- Has selection: {has_selection}
- Has error: {has_error}

Respond with JSON only:
{{
    "task_type": "<task type>",
    "confidence": <0.0-1.0>,
    "requires_file_context": <true/false>,
    "requires_terminal": <true/false>,
    "estimated_complexity": "<low/medium/high>",
    "reasoning": "<brief explanation>"
}}
"""


class TaskClassifier:
    """
    Handles LLM-based and fallback task classification.
    
    Uses Groq llama-3.3-70b-versatile as primary, with Cerebras fallback.
    Falls back to keyword-based classification if no models available.
    """
    
    def __init__(self, model_router: ModelRouter):
        self.model_router = model_router
        agent_logger.info("📋 TaskClassifier initialized (6 tool-aligned categories)")
    
    async def classify(
        self,
        query: str,
        current_file: Optional[str] = None,
        has_selection: bool = False,
        has_error: bool = False
    ) -> TaskClassification:
        """
        Classify user query into a task type.
        
        Args:
            query: User's query text
            current_file: Currently open file (if any)
            has_selection: Whether user has code selected
            has_error: Whether there's an error in terminal
            
        Returns:
            TaskClassification with task type and metadata
        """
        agent_logger.info(f"🔍 Classifying query: {query[:100]}...")
        
        # Build classification prompt
        prompt = CLASSIFICATION_PROMPT.format(
            query=query,
            current_file=current_file or "None",
            has_selection=has_selection,
            has_error=has_error
        )
        
        # Select classification model using TASK_MODELS priority chain
        # This aligns with execution priority: Cerebras first, then Ollama cloud, then Groq
        from ..config import AgentConfig
        model = None
        provider = "unknown"
        model_name = "unknown"

        for prov, model_key in AgentConfig.get_models_for_task("classification"):
            candidate = self.model_router.get_model_for_provider(prov, model_key)
            if candidate is not None:
                model = candidate
                provider = prov
                provider_config = AgentConfig.get_provider(prov)
                model_name = (
                    provider_config.models[model_key].name
                    if provider_config and model_key in provider_config.models
                    else model_key
                )
                agent_logger.info(f"Classification using: {provider}/{model_name}")
                break

        if model is None:
            agent_logger.warning("No model available for classification — using keyword fallback")
            return self._fallback_classification(query)

        # Log which model we're using
        log_model_call(provider, model_name, "classification")
        
        try:
            messages = [HumanMessage(content=prompt)]
            response = await model.ainvoke(messages)
            
            content = response.content
            agent_logger.debug(f"Raw LLM response ({len(content)} chars):")
            agent_logger.debug(content[:500] + ("..." if len(content) > 500 else ""))
            
            log_model_response(provider, model_name, len(content), success=True)
            
            # Parse JSON response
            # Strip <think>...</think> tags (some models include reasoning)
            if "<think>" in content:
                agent_logger.debug("Stripping <think> tags from response")
                content = content.split("</think>")[-1].strip()
            
            # Extract JSON from markdown code blocks
            if "```json" in content:
                agent_logger.debug("Extracting JSON from ```json block")
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                agent_logger.debug("Extracting JSON from ``` block")
                content = content.split("```")[1].split("```")[0]
            
            content = content.strip()
            agent_logger.debug(f"Cleaned content: {content[:200]}...")
            
            # Parse JSON
            try:
                data = json.loads(content)
                agent_logger.debug(f"✅ Successfully parsed JSON: {data}")
            except json.JSONDecodeError as je:
                agent_logger.error(f"❌ JSON parse error: {je}")
                agent_logger.error(f"Problematic content: {content[:500]}")
                
                # Try regex extraction as fallback
                import re
                agent_logger.debug("Attempting regex JSON extraction...")
                json_match = re.search(r'\{[^}]+\}', content, re.DOTALL)
                if json_match:
                    extracted = json_match.group(0)
                    agent_logger.debug(f"Regex extracted: {extracted}")
                    data = json.loads(extracted)
                else:
                    agent_logger.error("Regex extraction failed, using fallback")
                    raise je
            
            # Map task type to new enum
            task_type_str = data.get("task_type", "chat")
            task_type = self._map_task_type(task_type_str)
            
            classification = TaskClassification(
                task_type=task_type,
                confidence=float(data.get("confidence", 0.8)),
                requires_file_context=data.get("requires_file_context", False),
                requires_terminal=data.get("requires_terminal", False),
                estimated_complexity=data.get("estimated_complexity", "low"),
                reasoning=data.get("reasoning", "")
            )
            
            log_classification(
                classification.task_type.value,
                classification.confidence,
                classification.reasoning
            )
            
            return classification
            
        except Exception as e:
            agent_logger.error(f"❌ Classification error: {type(e).__name__}: {e}")
            agent_logger.warning("Falling back to keyword-based classification")
            return self._fallback_classification(query)
    
    def _map_task_type(self, task_type_str: str) -> TaskType:
        """Map string to TaskType enum, handling legacy values."""
        # Direct mapping
        try:
            return TaskType(task_type_str)
        except ValueError:
            pass
        
        # Legacy mapping from old 11-category system
        legacy_map = {
            "code_explain_simple": TaskType.CODE_INTELLIGENCE,
            "code_explain_complex": TaskType.CODE_INTELLIGENCE,
            "code_generation": TaskType.FILE_OPERATIONS,
            "code_generation_multi": TaskType.FILE_OPERATIONS,
            "bug_fixing": TaskType.FILE_OPERATIONS,
            "refactor": TaskType.FILE_OPERATIONS,
            "architecture": TaskType.CODE_INTELLIGENCE,
            "test_generation": TaskType.FILE_OPERATIONS,
            "documentation": TaskType.FILE_OPERATIONS,
            "research": TaskType.WEB,
        }
        
        return legacy_map.get(task_type_str, TaskType.CHAT)
    
    def _fallback_classification(self, query: str) -> TaskClassification:
        """
        Simple keyword-based fallback classification.
        
        Used when LLM is unavailable or fails.
        
        Args:
            query: User's query text
            
        Returns:
            TaskClassification based on keyword matching
        """
        query_lower = query.lower()
        
        # File operations keywords
        if any(kw in query_lower for kw in ["create", "write", "modify", "edit", "delete", "rename", "fix", "update", "change", "add"]):
            return TaskClassification(
                task_type=TaskType.FILE_OPERATIONS,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=False,
                estimated_complexity="medium",
                reasoning="Detected file modification keywords"
            )
        
        # Search keywords
        if any(kw in query_lower for kw in ["find", "search", "where", "locate", "grep", "look for"]):
            return TaskClassification(
                task_type=TaskType.SEARCH,
                confidence=0.7,
                requires_file_context=False,
                requires_terminal=False,
                estimated_complexity="low",
                reasoning="Detected search keywords"
            )
        
        # Execution keywords
        if any(kw in query_lower for kw in ["run", "execute", "install", "pip", "npm", "compile", "build"]):
            return TaskClassification(
                task_type=TaskType.EXECUTION,
                confidence=0.7,
                requires_file_context=False,
                requires_terminal=True,
                estimated_complexity="low",
                reasoning="Detected command execution keywords"
            )
        
        # Web keywords
        if any(kw in query_lower for kw in ["fetch", "url", "http", "documentation", "web"]):
            return TaskClassification(
                task_type=TaskType.WEB,
                confidence=0.7,
                requires_file_context=False,
                requires_terminal=False,
                estimated_complexity="low",
                reasoning="Detected web/URL keywords"
            )
        
        # Code intelligence keywords
        if any(kw in query_lower for kw in ["explain", "what does", "how does", "definition", "references", "error", "debug"]):
            return TaskClassification(
                task_type=TaskType.CODE_INTELLIGENCE,
                confidence=0.7,
                requires_file_context=True,
                requires_terminal=False,
                estimated_complexity="low",
                reasoning="Detected code understanding keywords"
            )
        
        # Default to chat
        return TaskClassification(
            task_type=TaskType.CHAT,
            confidence=0.5,
            requires_file_context=False,
            requires_terminal=False,
            estimated_complexity="low",
            reasoning="No specific tool category detected, defaulting to chat"
        )
