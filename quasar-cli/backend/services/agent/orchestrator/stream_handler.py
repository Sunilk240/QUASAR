"""
Stream Event Handler

Generates rich streaming events for the CLI and web interface.
Provides structured event types for real-time progress updates.
"""

from typing import Dict, Any, List, Optional
import time

from ..types import StreamEvent, StreamEventType
from ..logger import agent_logger


class StreamHandler:
    """
    Handles streaming event generation.
    
    Provides methods to emit various event types for real-time
    progress tracking and user feedback.
    """
    
    def __init__(self):
        agent_logger.debug("📡 StreamHandler initialized")
    
    def emit_classification(
        self,
        task_type: str,
        confidence: float,
        reasoning: str = ""
    ) -> Dict[str, Any]:
        """Emit task classification result."""
        return {
            "type": StreamEventType.CLASSIFICATION,
            "task_type": task_type,
            "confidence": confidence,
            "reasoning": reasoning,
            "timestamp": time.time()
        }
    
    def emit_thinking(self, content: str) -> Dict[str, Any]:
        """Emit when model is reasoning before action."""
        return {
            "type": StreamEventType.THINKING,
            "content": content,
            "timestamp": time.time()
        }
    
    def emit_plan(self, steps: List[str]) -> Dict[str, Any]:
        """Emit structured plan before execution."""
        return {
            "type": StreamEventType.PLAN,
            "steps": steps,
            "total_steps": len(steps),
            "timestamp": time.time()
        }
    
    def emit_iteration(
        self,
        current: int,
        max_iterations: int,
        remaining: int
    ) -> Dict[str, Any]:
        """Emit iteration progress."""
        return {
            "type": StreamEventType.ITERATION,
            "current": current,
            "max": max_iterations,
            "remaining": remaining,
            "timestamp": time.time()
        }
    
    def emit_iteration_warning(
        self,
        remaining: int,
        message: str
    ) -> Dict[str, Any]:
        """Emit warning when iterations are running low."""
        return {
            "type": StreamEventType.ITERATION_WARNING,
            "remaining": remaining,
            "message": message,
            "timestamp": time.time()
        }
    
    def emit_tool_start(
        self,
        tool: str,
        args: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Emit when tool execution starts."""
        return {
            "type": StreamEventType.TOOL_START,
            "tool": tool,
            "args": args,
            "timestamp": time.time()
        }
    
    def emit_tool_progress(
        self,
        tool: str,
        progress: float,
        message: str
    ) -> Dict[str, Any]:
        """
        Emit progress during long-running tools.
        
        Args:
            tool: Tool name
            progress: Progress from 0.0 to 1.0
            message: Human-readable progress message
        """
        return {
            "type": StreamEventType.TOOL_PROGRESS,
            "tool": tool,
            "progress": progress,
            "message": message,
            "timestamp": time.time()
        }
    
    def emit_tool_complete(
        self,
        tool: str,
        result: Any,
        success: bool = True
    ) -> Dict[str, Any]:
        """Emit when tool execution completes."""
        return {
            "type": StreamEventType.TOOL_COMPLETE,
            "tool": tool,
            "result": str(result)[:500] if result else "",  # Truncate long results
            "success": success,
            "timestamp": time.time()
        }
    
    def emit_observation(
        self,
        tool: str,
        observation: str
    ) -> Dict[str, Any]:
        """Emit model's interpretation of tool result."""
        return {
            "type": StreamEventType.OBSERVATION,
            "tool": tool,
            "observation": observation,
            "timestamp": time.time()
        }
    
    def emit_file_changed(
        self,
        path: str,
        action: str,  # created, modified, deleted
        lines: int = 0
    ) -> Dict[str, Any]:
        """Emit when file system changes."""
        return {
            "type": StreamEventType.FILE_CHANGED,
            "path": path,
            "action": action,
            "lines": lines,
            "timestamp": time.time()
        }
    
    def emit_command_output(
        self,
        output: str,
        is_error: bool = False
    ) -> Dict[str, Any]:
        """Emit terminal command output."""
        return {
            "type": StreamEventType.COMMAND_OUTPUT,
            "output": output,
            "is_error": is_error,
            "timestamp": time.time()
        }
    
    def emit_message(self, content: str) -> Dict[str, Any]:
        """Emit general message to user."""
        return {
            "type": StreamEventType.MESSAGE,
            "content": content,
            "timestamp": time.time()
        }
    
    def emit_token(self, content: str) -> Dict[str, Any]:
        """Emit streaming token from model response."""
        return {
            "type": StreamEventType.TOKEN,
            "content": content,
            "timestamp": time.time()
        }
    
    def emit_debug(self, content: str) -> Dict[str, Any]:
        """Emit debug information."""
        return {
            "type": StreamEventType.DEBUG,
            "content": content,
            "timestamp": time.time()
        }
    
    def emit_done(
        self,
        model: str,
        provider: str,
        task_type: str,
        iterations: int,
        tool_calls_count: int,
        tools_used: List[str],
        **kwargs
    ) -> Dict[str, Any]:
        """Emit completion signal."""
        return {
            "type": StreamEventType.DONE,
            "model": model,
            "provider": provider,
            "task_type": task_type,
            "iterations": iterations,
            "tool_calls_count": tool_calls_count,
            "tools_used": tools_used,
            "timestamp": time.time(),
            **kwargs
        }
    
    def emit_error(
        self,
        message: str,
        error_type: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Emit error event."""
        event = {
            "type": StreamEventType.ERROR,
            "message": message,
            "timestamp": time.time()
        }
        
        if error_type:
            event["error_type"] = error_type
        
        if details:
            event["details"] = details
        
        return event
