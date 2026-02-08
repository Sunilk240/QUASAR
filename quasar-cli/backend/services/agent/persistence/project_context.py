"""
Project Context Management

Manages .quasar/ directory and project-level context.
Provides persistent memory across sessions.
"""

from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import json

from ..logger import agent_logger


class ProjectContext:
    """
    Manages .quasar/ directory and project-level context.
    
    Creates and maintains:
    - context.md: Project-specific rules and information
    - memory.json: Session history and preferences
    - checkpoints/: For task recovery (future)
    """
    
    QUASAR_DIR = ".quasar"
    CONTEXT_FILE = "context.md"
    MEMORY_FILE = "memory.json"
    
    def __init__(self, workspace: Path):
        """
        Initialize project context.
        
        Args:
            workspace: Path to project workspace
        """
        self.workspace = Path(workspace)
        self.quasar_dir = self.workspace / self.QUASAR_DIR
        agent_logger.debug(f"ProjectContext initialized for: {workspace}")
    
    def initialize(self) -> bool:
        """
        Create .quasar/ directory if it doesn't exist.
        
        Returns:
            True if newly created, False if already existed
        """
        if not self.quasar_dir.exists():
            agent_logger.info(f"Creating .quasar/ directory in {self.workspace}")
            self.quasar_dir.mkdir(parents=True, exist_ok=True)
            self._create_default_context()
            self._create_empty_memory()
            self._create_hooks_directory()  # Create hooks with templates
            self._create_mcp_config()  # Create MCP config template
            agent_logger.info("✅ .quasar/ directory created with templates")
            return True  # Newly created
        
        # Ensure hooks directory exists even if .quasar/ already exists
        hooks_dir = self.quasar_dir / "hooks"
        if not hooks_dir.exists():
            self._create_hooks_directory()
        
        # Ensure mcp.json exists even if .quasar/ already exists
        mcp_file = self.quasar_dir / "mcp.json"
        if not mcp_file.exists():
            self._create_mcp_config()
        
        # Ensure context.md exists even if .quasar/ already exists
        context_file = self.quasar_dir / self.CONTEXT_FILE
        if not context_file.exists():
            self._create_default_context()
            agent_logger.info("✅ Created missing context.md template")
        
        # Ensure memory.json exists
        memory_file = self.quasar_dir / self.MEMORY_FILE
        if not memory_file.exists():
            self._create_empty_memory()
        
        agent_logger.debug(".quasar/ directory already exists")
        return False  # Already existed
    
    def _create_default_context(self):
        """Create default context.md template."""
        template = '''# QUASAR Project Context

## Project Description
<!-- Describe your project here. QUASAR will use this to understand context. -->

This is a new project. Add a description to help QUASAR understand your goals.

## Code Style
<!-- Your preferred coding style, conventions, etc. -->

- Use type hints for all functions
- Prefer async/await for I/O operations
- Follow PEP 8 for Python code
- Use meaningful variable names

## Important Files
<!-- List key files QUASAR should be aware of -->

- main.py: Entry point
- config.py: Configuration
- README.md: Project documentation

## Common Commands
<!-- Commands you frequently use in this project -->

- `pip install -r requirements.txt`: Install dependencies
- `python main.py`: Run the application
- `pytest`: Run tests

## Project Rules
<!-- Custom rules for QUASAR to follow in this project -->

- Always create tests for new functions
- Use .env for sensitive configuration
- Document all public APIs
- Keep functions under 50 lines when possible

## Notes
<!-- Any other information QUASAR should know -->

Add any project-specific notes, conventions, or context here.
'''
        context_file = self.quasar_dir / self.CONTEXT_FILE
        context_file.write_text(template, encoding='utf-8')
        agent_logger.debug(f"Created default context.md")
    
    def _create_empty_memory(self):
        """Create empty memory.json."""
        memory = {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "preferences": {},
            "recent_files": [],
            "session_history": []
        }
        self._save_memory(memory)
        agent_logger.debug("Created empty memory.json")
    
    def _create_hooks_directory(self):
        """Create hooks/ directory with template files."""
        hooks_dir = self.quasar_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        
        # Safety hooks template
        safety_template = '''"""
Example Safety Hooks for QUASAR

These hooks demonstrate how to add safety checks to prevent
dangerous operations.

To use: Rename to safety.py and customize as needed.
"""

from backend.services.agent.hooks import hook, HookPoint, HookResult


@hook(HookPoint.PRE_TOOL_USE)
def block_env_writes(context):
    """Block writes to .env files."""
    tool_name = context.get("tool_name")
    args = context.get("args", {})
    
    if tool_name in ["create_file", "modify_file", "patch_file"]:
        path = args.get("path", "")
        if path.endswith(".env") or "/.env" in path or "\\\\.env" in path:
            return HookResult(
                allow=False,
                message="❌ Blocked: Cannot automatically write to .env files"
            )
    
    return HookResult(allow=True)
'''
        (hooks_dir / "safety.py.template").write_text(safety_template, encoding='utf-8')
        
        # Logging hooks template
        logging_template = '''"""
Example Logging Hooks for QUASAR

Logs all tool usage for auditing and debugging.

To use: Rename to logging.py and customize as needed.
"""

from backend.services.agent.hooks import hook, HookPoint, HookResult
import logging

logger = logging.getLogger("quasar_hooks")


@hook(HookPoint.POST_TOOL_USE)
def log_tool_usage(context):
    """Log every tool call."""
    tool_name = context.get("tool_name")
    result = context.get("result", "")[:100]
    logger.info(f"Tool: {tool_name} - Result: {result}...")
    return HookResult(allow=True)


@hook(HookPoint.ON_COMPLETE)
def log_completion(context):
    """Log task completion."""
    task_type = context.get("task_type")
    tools_used = context.get("tools_used", [])
    logger.info(f"Completed: {task_type} using {len(tools_used)} tools")
    return HookResult(allow=True)
'''
        (hooks_dir / "logging.py.template").write_text(logging_template, encoding='utf-8')
        
        agent_logger.debug("Created hooks/ directory with templates")
    
    def _create_mcp_config(self):
        """Create MCP config template in project's .quasar/ directory."""
        mcp_config = '''{
  "mcpServers": {
    "_comment": "MCP servers are OPTIONAL. QUASAR works without them.",
    "_example_fetch": {
      "command": ["python", "-m", "mcp_server_fetch"],
      "disabled": true,
      "description": "Example: Python-based fetch server (pip install mcp-server-fetch)"
    },
    "_example_filesystem": {
      "command": ["python", "-m", "mcp_server_filesystem", "--allowed-paths", "."],
      "disabled": true,
      "description": "Example: Filesystem access server"
    }
  }
}
'''
        mcp_path = self.quasar_dir / "mcp.json"
        mcp_path.write_text(mcp_config, encoding='utf-8')
        agent_logger.debug("Created mcp.json template")
    
    def get_context(self) -> Optional[str]:
        """
        Read project context.md content.
        
        Returns:
            Context content or None if file doesn't exist
        """
        context_file = self.quasar_dir / self.CONTEXT_FILE
        if context_file.exists():
            try:
                content = context_file.read_text(encoding='utf-8')
                agent_logger.debug(f"Loaded context.md ({len(content)} chars)")
                return content
            except Exception as e:
                agent_logger.error(f"Error reading context.md: {e}")
                return None
        return None
    
    def get_memory(self) -> Dict[str, Any]:
        """
        Read memory.json.
        
        Returns:
            Memory dictionary or empty dict if file doesn't exist
        """
        memory_file = self.quasar_dir / self.MEMORY_FILE
        if memory_file.exists():
            try:
                content = memory_file.read_text(encoding='utf-8')
                memory = json.loads(content)
                agent_logger.debug(f"Loaded memory.json")
                return memory
            except Exception as e:
                agent_logger.error(f"Error reading memory.json: {e}")
                return {}
        return {}
    
    def _save_memory(self, memory: Dict[str, Any]):
        """
        Save memory.json.
        
        Args:
            memory: Memory dictionary to save
        """
        try:
            memory_file = self.quasar_dir / self.MEMORY_FILE
            memory_file.write_text(
                json.dumps(memory, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            agent_logger.debug("Saved memory.json")
        except Exception as e:
            agent_logger.error(f"Error saving memory.json: {e}")
    
    def add_to_history(self, query: str, response_summary: str):
        """
        Add interaction to session history.
        
        Args:
            query: User's query
            response_summary: Summary of agent's response
        """
        memory = self.get_memory()
        
        # Add new entry
        memory.setdefault("session_history", []).append({
            "timestamp": datetime.now().isoformat(),
            "query": query[:200],  # Truncate long queries
            "summary": response_summary[:500]  # Truncate long summaries
        })
        
        # Keep only last 50 interactions
        memory["session_history"] = memory["session_history"][-50:]
        
        self._save_memory(memory)
        agent_logger.debug(f"Added to session history: {query[:50]}...")
    
    def record_file_access(self, path: str):
        """
        Track recently accessed files.
        
        Args:
            path: File path that was accessed
        """
        memory = self.get_memory()
        recent = memory.setdefault("recent_files", [])
        
        # Remove if already in list (to move to front)
        if path in recent:
            recent.remove(path)
        
        # Add to front
        recent.insert(0, path)
        
        # Keep only last 20
        memory["recent_files"] = recent[:20]
        
        self._save_memory(memory)
        agent_logger.debug(f"Recorded file access: {path}")
    
    def set_preference(self, key: str, value: Any):
        """
        Set a user preference.
        
        Args:
            key: Preference key
            value: Preference value
        """
        memory = self.get_memory()
        memory.setdefault("preferences", {})[key] = value
        self._save_memory(memory)
        agent_logger.debug(f"Set preference: {key} = {value}")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        Get a user preference.
        
        Args:
            key: Preference key
            default: Default value if not found
            
        Returns:
            Preference value or default
        """
        memory = self.get_memory()
        return memory.get("preferences", {}).get(key, default)
    
    def get_recent_context_summary(self, max_entries: int = 3) -> str:
        """
        Get a summary of recent session history.
        
        Args:
            max_entries: Maximum number of recent entries to include
            
        Returns:
            Formatted summary string
        """
        memory = self.get_memory()
        history = memory.get("session_history", [])
        
        if not history:
            return ""
        
        recent = history[-max_entries:]
        lines = ["## Recent Session History"]
        
        for entry in recent:
            query = entry.get("query", "")[:100]
            summary = entry.get("summary", "")[:100]
            lines.append(f"- User: {query}...")
            if summary:
                lines.append(f"  Result: {summary}...")
        
        return "\n".join(lines)
    
    def exists(self) -> bool:
        """
        Check if .quasar/ directory exists.
        
        Returns:
            True if directory exists
        """
        return self.quasar_dir.exists()
