"""
Terminal Integration Tools for AI Agent

LangChain tools for:
- Suggesting commands for user to run
- Checking command availability

Note: Agent suggests commands but does NOT execute them.
User maintains full control over command execution.
"""

import shutil
from typing import Dict, Any
from langchain_core.tools import tool

# Import logging
from ..logger import agent_logger


@tool
def suggest_command(command: str, description: str = "") -> Dict[str, Any]:
    """
    Suggest a terminal command for the user to run manually.
    
    USE THIS to recommend commands to the user.
    The agent does NOT execute commands - user maintains full control.
    
    Args:
        command: The shell command to suggest (e.g., "pip install flask", "npm run dev")
        description: Optional description of what the command does
        
    Returns:
        Dictionary with the suggested command formatted for user display
    """
    agent_logger.info(f"💡 Tool: suggest_command({command[:50]}...)")
    
    return {
        "success": True,
        "type": "suggested_command",
        "command": command,
        "description": description or f"Run this command in your terminal",
        "message": f"Please run this command in your terminal:\n```\n{command}\n```"
    }


@tool
def check_command_available(command: str) -> Dict[str, Any]:
    """
    Check if a command is available in the system.
    
    Args:
        command: Command name to check (e.g., "python", "node", "git")
        
    Returns:
        Dictionary with availability status
    """
    path = shutil.which(command)
    
    if path:
        return {
            "available": True,
            "command": command,
            "path": path
        }
    else:
        return {
            "available": False,
            "command": command,
            "message": f"Command '{command}' not found in PATH"
        }


# Export terminal tools (only suggest and check)
TERMINAL_TOOLS = [
    suggest_command,
    check_command_available
]
