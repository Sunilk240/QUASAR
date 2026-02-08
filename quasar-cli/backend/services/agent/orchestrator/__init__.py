"""
Orchestrator Package

Modular orchestration system for the AI agent.

This package replaces the monolithic orchestrator.py with a clean,
modular architecture:

- coordinator.py: Main orchestrator (thin coordination layer)
- classifier.py: Task classification
- prompt_builder.py: System prompt construction
- executor.py: Tool execution and agentic loop
- stream_handler.py: SSE event generation

Usage:
    from services.agent.orchestrator import Orchestrator
    
    orchestrator = Orchestrator(workspace_path="/path/to/workspace")
    result = await orchestrator.process(query="create hello.py")
"""

from .coordinator import Orchestrator
from .classifier import TaskClassifier, TaskClassification
from .prompt_builder import PromptBuilder
from .executor import AgenticExecutor
from .stream_handler import StreamHandler

__all__ = [
    "Orchestrator",
    "TaskClassifier",
    "TaskClassification",
    "PromptBuilder",
    "AgenticExecutor",
    "StreamHandler"
]
