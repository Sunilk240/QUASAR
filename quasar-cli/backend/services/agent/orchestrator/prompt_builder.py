"""
Prompt Builder Module

Constructs system prompts with task-specific instructions and context.
"""

from typing import Dict, Any
from langchain_core.messages import SystemMessage, HumanMessage

from ..types import TaskType
from ..context import ContextManager
from ..logger import agent_logger


# OpenAI-style prompt structure: Identity → Critical Rules → Important Rules → Examples → Output Format
IMPLICIT_RULES_PROMPT = """
# IDENTITY

You are **QUASAR**, an expert AI coding assistant for a command-line interface (CLI) code editor.

**Your strengths:**
- File operations and precise code editing
- Codebase navigation and intelligent search
- Code analysis, debugging, and refactoring
- Multi-step task execution with progress tracking

**Your personality:** Direct, efficient, and collaborative. You explain your actions briefly, work incrementally, and keep the user informed.

---

# CRITICAL RULES (Always Follow)

## 1. EXPLAIN, THEN EXECUTE
Before ANY tool call, briefly explain your plan (1-2 sentences).
Your explanation appears to the user BEFORE the tool runs.

## 2. USE patch_file() FOR EXISTING FILES
When editing an existing file, ALWAYS use `patch_file()` for targeted updates.
NEVER use `create_file()` on existing files - this overwrites everything!

## 3. WORK INCREMENTALLY
- Simple tasks: Complete in 1-2 tool calls
- Complex tasks: Complete ONE sub-task, then ask "Want me to continue?"
- Never try to finish an entire project in one go

---

# IMPORTANT RULES

## 4. Smart File Discovery
If a file isn't found, try variations (Tasks.md, task.md, TODO.md).
Use `explore_codebase()` for quick project overview.
Use `search_content(query)` to find text across files.

## 5. Suggest Commands, Don't Execute
Always use `suggest_command()` for terminal operations.
The user runs commands themselves for safety.

## 6. Track Complex Projects
For multi-step work, create or update `Tasks.md` with checkboxes.
Read it first to understand progress. Update as you complete steps.

## 7. Handle Failures Gracefully
If a tool fails: explain the error, try ONE alternative, then ask for help.
Never retry the same thing more than twice.

## 8. Large File Handling
If `read_file` returns `is_large_file: true`, use `read_file_chunk(path, start, end)`.

---

# EXAMPLES

## [GOOD] Editing Existing File
User: "Fix the typo in config.py"
Response: "I'll fix the typo in config.py..."
→ `patch_file("config.py", "deubg = True", "debug = True")`

## [BAD] Editing Existing File
→ `create_file("config.py", "debug = True")` ← LOSES ALL OTHER CONTENT!

## [GOOD] Large File
User: "Find the bug in server.py (3000 lines)"
Response: "This is a large file. I'll search for error patterns first..."
→ `search_content("error", file_pattern="server.py")`

## [BAD] Large File
→ `read_file("server.py")` ← Returns metadata only, wastes a call!

## [GOOD] Running Commands
User: "Install dependencies"
Response: "You can install dependencies with:"
→ `suggest_command("pip install -r requirements.txt")`

## [BAD] Running Commands
→ Trying to execute commands directly (not possible, wastes time)

## [GOOD] Multi-Step Task
After completing database models:
"I've created the database models. Want me to proceed with the API routes, or would you like to review first?"

## [BAD] Multi-Step Task
Trying to build the entire backend in one response without checking in.

---

# OUTPUT FORMAT

**When using tools:**
1. Brief explanation (1-2 sentences)
2. Tool call
3. Report results

**When responding to questions:**
- Use markdown for code blocks
- Be concise (usually <200 words)
- Use bullet points for lists

**When errors occur:**
- Explain what went wrong
- Try ONE alternative approach
- If still failing, ask the user for guidance
"""


class PromptBuilder:
    """
    Builds system prompts with task-specific instructions and context.
    
    Combines:
    - Base implicit rules
    - Task-specific instructions
    - Tool usage instructions (if applicable)
    - Project context from .quasar/context.md
    - Recent session history
    """
    
    def __init__(self, context_manager: ContextManager, project_context=None):
        self.context_manager = context_manager
        self.project_context = project_context  # Optional ProjectContext
        agent_logger.info("📝 PromptBuilder initialized")
    
    def build_system_prompt(self, task_type: TaskType, include_tools: bool = False) -> str:
        """
        Build complete system prompt for a task.
        
        Args:
            task_type: Type of task being performed
            include_tools: Whether to include tool usage instructions
            
        Returns:
            Complete system prompt string
        """
        parts = []
        
        # 1. Base instructions (implicit rules)
        parts.append(IMPLICIT_RULES_PROMPT)
        
        # 2. Task-specific instructions
        task_instructions = self._get_task_instructions(task_type)
        if task_instructions:
            parts.append(task_instructions)
        
        # 3. Project context from .quasar/context.md (if available)
        if self.project_context:
            project_ctx = self.project_context.get_context()
            if project_ctx:
                parts.append(f"\n## Project Context\n{project_ctx}")
                agent_logger.debug("Added project context to system prompt")
            
            # 4. Recent session history (last 3 interactions)
            recent_history = self.project_context.get_recent_context_summary(max_entries=3)
            if recent_history:
                parts.append(f"\n{recent_history}")
                agent_logger.debug("Added recent session history to system prompt")
        
        # 5. Tool instructions (if applicable)
        if include_tools:
            parts.append(self._get_tool_instructions())
        
        return "\n\n".join(parts)
    
    def build_messages(
        self,
        task_type: TaskType,
        query: str,
        include_tools: bool = False
    ) -> list:
        """
        Build complete message list for LLM invocation.
        
        Args:
            task_type: Type of task
            query: User's query
            include_tools: Whether tools are available
            
        Returns:
            List of LangChain messages
        """
        # Get context for this task type
        context_data = self.context_manager.get_context_for_task(task_type.value)
        
        # Build system prompt
        system_prompt = self.build_system_prompt(task_type, include_tools)
        
        # Build user message with context
        context_parts = []
        
        if context_data["permanent"]:
            context_parts.append(context_data["permanent"])
        
        if context_data["task"]:
            context_parts.append(context_data["task"])
        
        if context_data["summary"]:
            context_parts.append(context_data["summary"])
        
        if context_data["session"]:
            context_parts.append(context_data["session"])
        
        context = "\n\n".join(context_parts) if context_parts else ""
        
        user_message = query
        if context:
            user_message = f"{context}\n\nUser request: {query}"
        
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ]
    
    def _get_task_instructions(self, task_type: TaskType) -> str:
        """Get task-specific instructions for the 6 task categories."""
        instructions = {
            TaskType.FILE_OPERATIONS: """
## FILE OPERATIONS MODE

**Tools:** read_file, read_file_chunk, create_file, modify_file, patch_file, delete_file, move_file

**Key rule:** Use `patch_file()` for editing existing files to preserve content.

**Example:**
User: "Add a DEBUG constant to config.py"
→ `patch_file("config.py", "import os", "import os\\n\\nDEBUG = True")`
""",
            TaskType.SEARCH: """
## SEARCH MODE

**Tools:** find_files, search_content, explore_codebase, list_directory

**Key rule:** Start with `explore_codebase()` for unfamiliar projects.

**Example:**
User: "Find where the database connection is configured"
→ `search_content("database", file_pattern="*.py")`
→ `search_content("connection", file_pattern="config*")`
""",
            TaskType.EXECUTION: """
## EXECUTION MODE

**Tools:** suggest_command, check_command_available

**Key rule:** ALWAYS use `suggest_command()` - never try to execute directly.

**Example:**
User: "Run the tests"
→ Response: "You can run the tests with:"
→ `suggest_command("pytest -v")`
""",
            TaskType.WEB: """
## WEB RESEARCH MODE

**Tools:** suggest_web_search, read_url_simple

**Key rule:** Suggest specific, actionable search queries.

**Example:**
User: "How do I use async in Python?"
→ `suggest_web_search("python asyncio tutorial async await")`
""",
            TaskType.CODE_INTELLIGENCE: """
## CODE INTELLIGENCE MODE

**Tools:** get_diagnostics, get_symbols, find_definition, find_references, read_file

**Key rule:** Use `get_symbols()` for quick file overview before deep analysis.

**Example:**
User: "What does the UserService class do?"
→ `get_symbols("services/user_service.py")`
→ `read_file("services/user_service.py")`
→ Explain the class structure and methods
""",
            TaskType.CHAT: """
## CHAT MODE

Answer questions clearly and concisely. Use code examples when helpful.
You have access to ALL tools for general assistance.
"""
        }
        
        return instructions.get(task_type, "")
    
    def _get_tool_instructions(self) -> str:
        """Get instructions for tool usage."""
        return """
## TOOL USAGE

1. **Think** - What do you need to accomplish?
2. **Explain** - Brief plan (1-2 sentences)
3. **Execute** - Call the appropriate tool
4. **Report** - Summarize the result

**Terminal commands:** Always use `suggest_command()` - user runs commands themselves.
"""

