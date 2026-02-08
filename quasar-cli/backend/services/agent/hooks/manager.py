"""
Hooks Manager

Manages lifecycle hooks that run at key points in the agent workflow.
"""

from enum import Enum
from typing import Callable, Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, field
import importlib.util
import asyncio
import logging

logger = logging.getLogger("hooks_manager")


class HookPoint(str, Enum):
    """Points in the agent lifecycle where hooks can run."""
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    ON_ERROR = "on_error"
    ON_COMPLETE = "on_complete"
    PRE_RESPONSE = "pre_response"


@dataclass
class HookResult:
    """Result from hook execution."""
    allow: bool = True  # If False, blocks the action
    modified_args: Optional[Dict[str, Any]] = None  # Modified arguments
    message: Optional[str] = None  # Message to display/log
    
    def __bool__(self):
        """Allow truthiness check."""
        return self.allow


class HooksManager:
    """
    Manages lifecycle hooks.
    
    Loads hooks from .quasar/hooks/ directory and executes them
    at appropriate points in the agent workflow.
    """
    
    def __init__(self, workspace: Path):
        """
        Initialize hooks manager.
        
        Args:
            workspace: Path to workspace directory
        """
        self.workspace = Path(workspace)
        self.hooks: Dict[HookPoint, List[Callable]] = {
            point: [] for point in HookPoint
        }
        self.hooks_dir = self.workspace / ".quasar" / "hooks"
        
        logger.info(f"🪝 HooksManager initialized for workspace: {workspace}")
        
        # Load hooks from .quasar/hooks/
        self._load_project_hooks()
    
    def _load_project_hooks(self):
        """Load hooks from .quasar/hooks/ directory."""
        if not self.hooks_dir.exists():
            logger.info("ℹ️ No hooks directory found, skipping hook loading")
            return
        
        hook_files = list(self.hooks_dir.glob("*.py"))
        if not hook_files:
            logger.info("ℹ️ No hook files found in .quasar/hooks/")
            return
        
        logger.info(f"📂 Loading hooks from {len(hook_files)} files...")
        
        for hook_file in hook_files:
            try:
                self._load_hook_file(hook_file)
            except Exception as e:
                logger.error(f"❌ Failed to load hook file {hook_file.name}: {e}")
        
        # Log summary
        total_hooks = sum(len(hooks) for hooks in self.hooks.values())
        if total_hooks > 0:
            logger.info(f"✅ Loaded {total_hooks} hooks:")
            for point, hooks in self.hooks.items():
                if hooks:
                    logger.info(f"   {point.value}: {len(hooks)} hook(s)")
    
    def _load_hook_file(self, path: Path):
        """
        Load hooks from a Python file.
        
        Args:
            path: Path to hook file
        """
        logger.debug(f"📄 Loading hook file: {path.name}")
        
        # Create module spec
        module_name = f"quasar_hook_{path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        
        if spec is None or spec.loader is None:
            logger.error(f"❌ Could not create module spec for {path.name}")
            return
        
        # Load module
        module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"❌ Error executing hook module {path.name}: {e}")
            return
        
        # Find decorated functions
        hooks_found = 0
        for name in dir(module):
            if name.startswith("_"):
                continue
            
            obj = getattr(module, name)
            
            # Check if it's a hook function
            if callable(obj) and hasattr(obj, "_hook_point"):
                hook_point = obj._hook_point
                self.hooks[hook_point].append(obj)
                hooks_found += 1
                logger.debug(f"   ✅ Registered hook: {name} at {hook_point.value}")
        
        if hooks_found > 0:
            logger.info(f"✅ Loaded {hooks_found} hook(s) from {path.name}")
    
    async def run_hooks(
        self, 
        point: HookPoint, 
        context: Dict[str, Any]
    ) -> HookResult:
        """
        Run all hooks for a given point.
        
        Args:
            point: Hook point to execute
            context: Context data for hooks
            
        Returns:
            HookResult with combined results from all hooks
        """
        hooks = self.hooks.get(point, [])
        
        if not hooks:
            # No hooks registered for this point
            return HookResult(allow=True)
        
        logger.debug(f"🪝 Running {len(hooks)} hook(s) at {point.value}")
        
        result = HookResult(allow=True)
        
        for hook_func in hooks:
            try:
                # Execute hook (async or sync)
                if asyncio.iscoroutinefunction(hook_func):
                    hook_result = await hook_func(context)
                else:
                    hook_result = hook_func(context)
                
                # Process hook result
                if hook_result is None:
                    # No result means allow
                    continue
                
                if isinstance(hook_result, HookResult):
                    # Check if hook blocks the action
                    if not hook_result.allow:
                        logger.info(f"🚫 Hook blocked action: {hook_result.message}")
                        result.allow = False
                        result.message = hook_result.message
                        break  # Stop processing hooks
                    
                    # Merge modified args
                    if hook_result.modified_args:
                        if result.modified_args is None:
                            result.modified_args = {}
                        result.modified_args.update(hook_result.modified_args)
                    
                    # Collect messages
                    if hook_result.message:
                        if result.message:
                            result.message += f"\n{hook_result.message}"
                        else:
                            result.message = hook_result.message
                
            except Exception as e:
                # Log error but don't break on hook errors
                logger.error(f"❌ Hook error in {hook_func.__name__}: {e}")
                # Continue with other hooks
        
        return result
    
    def has_hooks(self, point: HookPoint) -> bool:
        """
        Check if any hooks are registered for a point.
        
        Args:
            point: Hook point to check
            
        Returns:
            True if hooks exist for this point
        """
        return len(self.hooks.get(point, [])) > 0
    
    def get_hook_count(self, point: Optional[HookPoint] = None) -> int:
        """
        Get number of registered hooks.
        
        Args:
            point: Specific hook point, or None for total
            
        Returns:
            Number of hooks
        """
        if point:
            return len(self.hooks.get(point, []))
        return sum(len(hooks) for hooks in self.hooks.values())


def hook(point: HookPoint):
    """
    Decorator to mark function as a hook.
    
    Usage:
        @hook(HookPoint.PRE_TOOL_USE)
        def my_hook(context):
            # Hook logic here
            return HookResult(allow=True)
    
    Args:
        point: Hook point where this function should run
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        func._hook_point = point
        return func
    return decorator
