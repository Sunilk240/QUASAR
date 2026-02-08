"""
Lifecycle Hooks System

Allows custom code to run at key points in the agent lifecycle.
Hooks enable project-specific automation, safety checks, and customization.
"""

from .manager import HooksManager, HookPoint, HookResult, hook

__all__ = [
    "HooksManager",
    "HookPoint",
    "HookResult",
    "hook",
]
