"""
Shared type definitions for the agent system.

This module contains all common types used across the agent architecture.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum
import time


class TaskType(str, Enum):
    """
    Task types aligned with tool categories (Claude Code style).
    
    These map directly to tool selection for efficient routing.
    """
    # Core categories - map to tool sets
    FILE_OPERATIONS = "file_operations"    # read, write, edit files
    SEARCH = "search"                      # find files, search content
    EXECUTION = "execution"                # suggest commands
    WEB = "web"                           # fetch URLs, web search
    CODE_INTELLIGENCE = "code_intelligence"  # diagnostics, definitions
    
    # Fallback
    CHAT = "chat"                         # general Q&A, uses all tools


@dataclass
class TaskClassification:
    """Result of task classification."""
    task_type: TaskType
    confidence: float
    requires_file_context: bool
    requires_terminal: bool
    estimated_complexity: str  # low, medium, high
    reasoning: str


@dataclass
class AgentResponse:
    """Standard response from agent."""
    success: bool
    response: str
    task_type: str
    model_used: str
    provider: str
    tools_used: List[str] = field(default_factory=list)
    tool_calls_count: int = 0
    iterations: int = 1
    error: Optional[str] = None


@dataclass
class StreamEvent:
    """Single streaming event."""
    type: str  # classification, thinking, tool_start, tool_complete, token, done, error
    data: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            **self.data,
            "timestamp": self.timestamp
        }


class StreamEventType:
    """Constants for stream event types."""
    CLASSIFICATION = "classification"
    THINKING = "thinking"
    PLAN = "plan"
    ITERATION = "iteration"
    ITERATION_WARNING = "iteration_warning"
    TOOL_START = "tool_start"
    TOOL_PROGRESS = "tool_progress"
    TOOL_COMPLETE = "tool_complete"
    OBSERVATION = "observation"
    FILE_CHANGED = "file_changed"
    COMMAND_OUTPUT = "command_output"
    MESSAGE = "message"
    TOKEN = "token"
    DEBUG = "debug"
    DONE = "done"
    ERROR = "error"


@dataclass
class ExecutionResult:
    """Result from tool execution."""
    success: bool
    response: str
    tools_used: List[str]
    tool_calls_count: int
    iterations: int
    model_used: str
    provider: str
    error: Optional[str] = None
