"""
Terminal Integration Tools for AI Agent

LangChain tools for:
- Suggesting commands for user to run
- Checking command availability
- Executing commands with user confirmation gate (run_command)
"""

import re
import shutil
import subprocess
from typing import Dict, Any
from langchain_core.tools import tool

# Import logging
from ..logger import agent_logger


@tool
def suggest_command(command: str, description: str = "") -> Dict[str, Any]:
    """
    Suggest a terminal command for the user to run manually.
    
    USE THIS to recommend commands the user should run themselves.
    Use run_command() instead when you need to see the output (tests, builds, etc.).
    
    Args:
        command: The shell command to suggest (e.g., "pip install flask")
        description: Optional description of what the command does
        
    Returns:
        Dictionary with the suggested command formatted for user display
    """
    agent_logger.info(f"💡 Tool: suggest_command({command[:50]}...)")
    
    return {
        "success": True,
        "type": "suggested_command",
        "command": command,
        "description": description or "Run this command in your terminal",
        "message": f"Please run this command in your terminal:\n```\n{command}\n```",
    }


@tool
def check_command_available(command: str) -> Dict[str, Any]:
    """
    Check if a command is available in the system PATH.
    
    Args:
        command: Command name to check (e.g., "python", "node", "git")
        
    Returns:
        Dictionary with availability status
    """
    path = shutil.which(command)
    
    if path:
        return {"available": True, "command": command, "path": path}
    else:
        return {
            "available": False,
            "command": command,
            "message": f"Command '{command}' not found in PATH",
        }


# ---------------------------------------------------------------------------
# Safety patterns for run_command
# ---------------------------------------------------------------------------

# Always auto-execute — read-only / info commands
SAFE_PATTERNS = [
    r"^(ls|dir|pwd|echo|cat|head|tail|wc|type)\b",
    r"^git\s+(status|log|diff|branch|show|remote\s+-v|fetch|stash\s+list)\b",
    r"^(pytest|python\s+-m\s+pytest)\s*(--collect-only|--version|-h)(\s|$)",
    r"^(python|python3|node|npm|pip|pip3)\s+(--version|-V)$",
    r"^(which|where)\s+\w+$",
    r"^(env|set|printenv)\s*$",
]

# Always block — regardless of user response
DANGEROUS_PATTERNS = [
    r"rm\s+-[rRf]",
    r"\bsudo\b",
    r"\bmkfs\b",
    r"\bdd\b.*\bif=",
    r":\(\)\s*\{",
    r">\s*/dev/",
    r"\bformat\s+[a-zA-Z]:",
    r"\bchmod\s+777\b",
    r"\bshutdown\b|\breboot\b",
]


def _is_safe(command: str) -> bool:
    for pat in SAFE_PATTERNS:
        if re.match(pat, command.strip(), re.IGNORECASE):
            return True
    return False


def _is_dangerous(command: str) -> bool:
    for pat in DANGEROUS_PATTERNS:
        if re.search(pat, command, re.IGNORECASE):
            return True
    return False


def _execute_command(command: str) -> Dict[str, Any]:
    """Run a command and return stdout / stderr / exit_code."""
    from ..config import AgentConfig
    from .file_tools import get_workspace

    workspace = get_workspace() or "."
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(workspace),
            timeout=AgentConfig.TOOL_TIMEOUT_SECONDS,
        )
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-1000:],
            "command": command,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "Command timed out.",
            "command": command,
        }
    except Exception as exc:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "command": command,
        }


@tool
def run_command(command: str, reason: str = "") -> Dict[str, Any]:
    """
    Execute a terminal command and return its output (stdout, stderr, exit code).

    Use for: running tests (pytest), checking build output, verifying installs,
    reading git status/logs, running scripts after writing them.
    NEVER use for: rm -rf, sudo, format, shutdown, or any destructive operation.

    Dangerous commands are permanently blocked.
    Non-trivially-safe commands require explicit user confirmation — the executor
    HOLDS until the user clicks Allow or Deny. Never auto-proceeds on non-answer.

    Args:
        command: Shell command to run
        reason: Brief one-line explanation of why you are running this

    Returns:
        Dict with: success, exit_code, stdout, stderr, command.
        (blocked or requires_confirmation keys are handled internally by executor)
    """
    agent_logger.info(f"run_command requested: {command[:80]!r}")

    # Always block dangerous commands — no user override possible
    if _is_dangerous(command):
        agent_logger.warning(f"run_command BLOCKED (dangerous): {command[:80]!r}")
        return {
            "success": False,
            "blocked": True,
            "exit_code": -1,
            "stdout": "",
            "stderr": (
                "Blocked: matches a permanently-blocked pattern. "
                "Use suggest_command() to recommend it to the user instead."
            ),
            "command": command,
        }

    # Auto-execute safe read-only / info commands
    if _is_safe(command):
        agent_logger.info(f"run_command AUTO-APPROVED (safe): {command[:80]!r}")
        return _execute_command(command)

    # Everything else: register with gate and return sentinel.
    # executor.py detects this, yields command_confirmation_required, awaits the gate.
    agent_logger.info(f"run_command PENDING user confirmation: {command[:80]!r}")
    from .confirmation_gate import get_confirmation_gate
    gate = get_confirmation_gate()
    gate.request(command)

    return {
        "requires_confirmation": True,
        "command": command,
        "reason": reason or "No reason provided",
    }


# ---------------------------------------------------------------------------
# Exported tool list
# ---------------------------------------------------------------------------

TERMINAL_TOOLS = [
    suggest_command,
    check_command_available,
    run_command,
]
