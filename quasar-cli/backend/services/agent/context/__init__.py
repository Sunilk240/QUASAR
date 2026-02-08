"""
Context Management Package for AI Agent

Exports:
- ContextManager: Main context manager
- ConversationSummarizer: Summarizes conversation history
"""

from .manager import (
    ContextManager,
    PermanentContext,
    TaskContext,
    SessionMemory,
    ConversationMessage,
)

from .summarizer import (
    ConversationSummarizer,
    get_summarizer
)

__all__ = [
    "ContextManager",
    "PermanentContext",
    "TaskContext",
    "SessionMemory",
    "ConversationMessage",
    "ConversationSummarizer",
    "get_summarizer"
]

