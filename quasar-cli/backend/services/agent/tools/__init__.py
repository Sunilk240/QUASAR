"""
AI Agent Tools Package

Exports all tools for use with LangChain agents.
"""

from .file_tools import (
    FILE_TOOLS,
    read_file,
    read_file_chunk,
    create_file,
    modify_file,
    patch_file,
    delete_file,
    move_file,
    restore_backup,
    list_backups,
    show_diff,
    set_workspace,
    get_workspace
)

from .web_tools import (
    WEB_TOOLS,
    extract_relevant_content,
    tavily_search,
    duckduckgo_search,
    jina_reader,
    fetch_url_content,
    wikipedia_search,
    arxiv_search,
    github_search
)

from .terminal_tools import (
    TERMINAL_TOOLS,
    suggest_command,
    check_command_available,
    run_command,
    _execute_command as _terminal_execute_command,
)

from .search_tools import (
    SEARCH_TOOLS,
    find_files,
    search_content,
    explore_codebase,
    list_directory
)

from .code_intelligence import (
    CODE_INTELLIGENCE_TOOLS,
    get_diagnostics,
    get_symbols,
    find_definition,
    find_references
)

from .executor import (
    ToolExecutor,
    ToolExecutionResult,
    has_tool_calls,
    get_tool_calls
)


# All tools combined
ALL_TOOLS = FILE_TOOLS + TERMINAL_TOOLS + WEB_TOOLS + SEARCH_TOOLS + CODE_INTELLIGENCE_TOOLS

# Tool categories for selective use
TOOLS_BY_CATEGORY = {
    "read_only": [
        read_file, read_file_chunk, 
        find_files, search_content, explore_codebase, list_directory,
        check_command_available, tavily_search, duckduckgo_search, jina_reader, fetch_url_content,
        get_diagnostics, get_symbols, find_definition, find_references
    ],
    "write": [create_file, modify_file, patch_file, delete_file, move_file],
    "suggest": [suggest_command, check_command_available],
    "search": SEARCH_TOOLS,
    "web": WEB_TOOLS,
    "code_intelligence": CODE_INTELLIGENCE_TOOLS,
}


def get_tools_for_task(task_type: str) -> list:
    """
    Get appropriate tools for a task type.
    
    PRINCIPLE: Give each task type the MINIMUM tools needed + common helpers.
    
    Args:
        task_type: Type of task (file_operations, search, execution, web, code_intelligence, chat)
        
    Returns:
        List of tools appropriate for the task
    """
    # Task-specific tool mapping
    task_tools = {
        # File operations: edit files + search to find them
        "file_operations": FILE_TOOLS + SEARCH_TOOLS,
        
        # Search: find things + read to show results
        "search": SEARCH_TOOLS + FILE_TOOLS,
        
        # Execution: suggest commands + read scripts/configs + find files
        "execution": TERMINAL_TOOLS + FILE_TOOLS + SEARCH_TOOLS,
        
        # Web: fetch URLs + save to files + search existing docs
        "web": WEB_TOOLS + FILE_TOOLS + SEARCH_TOOLS,
        
        # Code intelligence: analyze + read + search
        "code_intelligence": CODE_INTELLIGENCE_TOOLS + FILE_TOOLS + SEARCH_TOOLS,
        
        # Chat: everything except terminal (safer for casual conversation)
        "chat": FILE_TOOLS + SEARCH_TOOLS + WEB_TOOLS + CODE_INTELLIGENCE_TOOLS + TERMINAL_TOOLS
    }
    
    return task_tools.get(task_type, ALL_TOOLS)

