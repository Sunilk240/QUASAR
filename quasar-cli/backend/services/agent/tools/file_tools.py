"""
File Operations Tools for AI Agent

LangChain tools for:
- Reading files
- Creating files
- Modifying files
- Deleting files
- Listing directories

All tools validate paths are within workspace.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
import os
from langchain_core.tools import tool

# Import logging and config
from ..logger import agent_logger
from ..config import AgentConfig

# Import backup manager
from .backup_manager import BackupManager


# Workspace will be set by the agent when initialized
_workspace_path: Optional[Path] = None
_backup_manager: Optional[BackupManager] = None


def set_workspace(path: str):
    """Set the current workspace path and initialize backup manager."""
    global _workspace_path, _backup_manager
    _workspace_path = Path(path)
    _backup_manager = BackupManager(_workspace_path)
    agent_logger.info(f"🔧 Tool workspace set: {path}")


def get_workspace() -> Path:
    """Get current workspace path."""
    global _workspace_path
    if _workspace_path is None:
        # Default to current directory if not set
        return Path(os.getcwd())
    return _workspace_path


def _count_lines_fast(path: Path) -> int:
    """Count lines without loading entire file into memory."""
    try:
        with path.open('rb') as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def validate_path(path: str) -> tuple[bool, str, Optional[Path]]:
    """
    Validate that path is safe and within workspace.
    
    Returns:
        (is_valid, error_message, resolved_path)
    """
    workspace = get_workspace()
    
    # Check for path traversal
    if ".." in path:
        agent_logger.warning(f"Path traversal attempt: {path}")
        return (False, "Path traversal (..) not allowed", None)
    
    # Block sensitive files (security)
    BLOCKED_FILES = {
        ".env", ".env.local", ".env.production", ".env.development",
        ".env.test", ".env.staging",
        "secrets.json", "credentials.json", "config.secret.json",
        ".aws/credentials", ".aws/config",
        ".ssh/id_rsa", ".ssh/id_ed25519", ".ssh/id_dsa",
        ".npmrc", ".pypirc",
    }
    
    BLOCKED_EXTENSIONS = {".pem", ".key", ".p12", ".pfx"}
    
    path_lower = path.lower()
    filename = Path(path).name.lower()
    file_ext = Path(path).suffix.lower()
    
    # Check exact filename matches
    for blocked in BLOCKED_FILES:
        if "/" in blocked:  # Path pattern like .aws/credentials
            if blocked in path_lower:
                agent_logger.warning(f"🚫 Blocked access to sensitive file: {path}")
                return (False, f"Access to sensitive file '{blocked}' is blocked for security", None)
        else:  # Filename pattern
            if filename == blocked or blocked in path_lower:
                agent_logger.warning(f"🚫 Blocked access to sensitive file: {path}")
                return (False, f"Access to sensitive file '{blocked}' is blocked for security", None)
    
    # Check file extensions
    if file_ext in BLOCKED_EXTENSIONS:
        agent_logger.warning(f"🚫 Blocked access to sensitive file type: {path}")
        return (False, f"Access to sensitive file type '{file_ext}' is blocked for security", None)
    
    # Resolve full path
    if Path(path).is_absolute():
        full_path = Path(path)
    else:
        full_path = workspace / path
    
    full_path = full_path.resolve()
    
    # Ensure path is within workspace
    try:
        full_path.relative_to(workspace)
    except ValueError:
        agent_logger.warning(f"Path outside workspace: {path}")
        return (False, f"Path must be within workspace: {workspace}", None)
    
    return (True, "", full_path)


# ============================================================================
# File Caching (10x faster for repeated reads)
# ============================================================================
from functools import lru_cache

@lru_cache(maxsize=20)
def _read_file_cached(path: str, mtime: float) -> str:
    """Read file with caching. Cache invalidates when file changes (mtime)."""
    return Path(path).read_text(encoding='utf-8')


def read_file_content(path: Path) -> str:
    """Read file content with caching support."""
    try:
        mtime = path.stat().st_mtime
        return _read_file_cached(str(path), mtime)
    except Exception:
        # Fallback to direct read if caching fails
        return path.read_text(encoding='utf-8')


def clear_file_cache():
    """Clear the file cache (call when files are modified)."""
    _read_file_cached.cache_clear()


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "jsx",
        ".tsx": "tsx",
        ".html": "html",
        ".css": "css",
        ".json": "json",
        ".md": "markdown",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".xml": "xml",
        ".sql": "sql",
        ".sh": "bash",
        ".ps1": "powershell",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
    }
    ext = Path(file_path).suffix.lower()
    return ext_map.get(ext, "text")


@tool
def read_file(path: str) -> Dict[str, Any]:
    """
    Read the contents of a file in the workspace.
    
    For large files (>2000 lines), returns metadata only and suggests using read_file_chunk.
    
    Args:
        path: File path relative to workspace (e.g., "src/main.py")
        
    Returns:
        Dictionary with content, language, and line count
    """
    agent_logger.info(f"🔧 Tool: read_file({path})")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        agent_logger.error(f"❌ read_file failed: {error}")
        return {"error": error}
    
    if not full_path.exists():
        agent_logger.error(f"❌ File not found: {path}")
        return {"error": f"File not found: {path}"}
    
    if not full_path.is_file():
        agent_logger.error(f"❌ Not a file: {path}")
        return {"error": f"Not a file: {path}"}
    
    try:
        # Fast check: count lines without loading content first (uses config)
        line_count = _count_lines_fast(full_path)
        size_bytes = full_path.stat().st_size
        
        # If file is too large, return metadata only (don't load content)
        if line_count > AgentConfig.MAX_FILE_LINES:
            agent_logger.warning(f"Large file detected: {path} ({line_count} lines). Returning metadata only.")
            return {
                "path": path,
                "language": detect_language(path),
                "lines": line_count,
                "size_bytes": size_bytes,
                "is_large_file": True,
                "max_lines_shown": 0,
                "hint": f"File has {line_count} lines. Use read_file_chunk(path, start_line, end_line) to read specific sections. Recommended chunk size: 500 lines."
            }
        
        # Only load content for small files (uses cache for repeated reads)
        content = read_file_content(full_path)
        
        agent_logger.info(f"read_file success: {path} ({len(content)} chars, {line_count} lines)")
        return {
            "content": content,
            "path": path,
            "language": detect_language(path),
            "lines": line_count,
            "size_bytes": size_bytes
        }
    except Exception as e:
        agent_logger.error(f"read_file error: {path} - {e}")
        return {"error": f"Failed to read file: {str(e)}"}


@tool
def read_file_chunk(path: str, start_line: int = 1, end_line: int = 500) -> Dict[str, Any]:
    """
    Read a specific chunk of a file by line numbers.
    
    Use this for large files that exceed the context limit.
    
    Args:
        path: File path relative to workspace
        start_line: Starting line number (1-indexed, inclusive)
        end_line: Ending line number (1-indexed, inclusive)
        
    Returns:
        Dictionary with chunk content, line range, and total lines
    """
    agent_logger.info(f"🔧 Tool: read_file_chunk({path}, lines {start_line}-{end_line})")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        agent_logger.error(f"❌ read_file_chunk failed: {error}")
        return {"error": error}
    
    if not full_path.exists():
        agent_logger.error(f"❌ File not found: {path}")
        return {"error": f"File not found: {path}"}
    
    if not full_path.is_file():
        agent_logger.error(f"❌ Not a file: {path}")
        return {"error": f"Not a file: {path}"}
    
    try:
        content = full_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        total_lines = len(lines)
        
        # Validate line range
        if start_line < 1:
            start_line = 1
        if end_line > total_lines:
            end_line = total_lines
        if start_line > end_line:
            return {"error": f"Invalid range: start_line ({start_line}) > end_line ({end_line})"}
        
        # Extract chunk (convert to 0-indexed)
        chunk_lines = lines[start_line - 1:end_line]
        chunk_content = "\n".join(chunk_lines)
        
        agent_logger.info(f"✅ read_file_chunk success: {path} lines {start_line}-{end_line} ({len(chunk_lines)} lines)")
        return {
            "content": chunk_content,
            "path": path,
            "language": detect_language(path),
            "start_line": start_line,
            "end_line": end_line,
            "lines_in_chunk": len(chunk_lines),
            "total_lines": total_lines,
            "has_more_before": start_line > 1,
            "has_more_after": end_line < total_lines
        }
    except Exception as e:
        agent_logger.error(f"❌ read_file_chunk error: {path} - {e}")
        return {"error": f"Failed to read file chunk: {str(e)}"}



@tool
def create_file(path: str, content: str, overwrite: bool = False) -> Dict[str, Any]:
    """
    Create a new file with the given content.
    
    Args:
        path: File path relative to workspace
        content: File content to write
        overwrite: If True, overwrite existing file
        
    Returns:
        Dictionary with success status and file info
    """
    agent_logger.info(f"🔧 Tool: create_file({path}, overwrite={overwrite})")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        agent_logger.error(f"❌ create_file failed: {error}")
        return {"error": error}
    
    if full_path.exists() and not overwrite:
        agent_logger.warning(f"⚠️ File exists, overwrite=False: {path}")
        return {
            "error": f"File already exists: {path}",
            "file_exists": True,
            "path": path,
            "hint": "Use overwrite=True to replace the existing file, or choose a different filename."
        }
    
    try:
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write file
        full_path.write_text(content, encoding="utf-8")
        
        agent_logger.info(f"✅ create_file success: {path} ({len(content)} chars)")
        return {
            "success": True,
            "path": path,
            "language": detect_language(path),
            "lines": len(content.split("\n")),
            "size_bytes": len(content.encode("utf-8"))
        }
    except Exception as e:
        agent_logger.error(f"❌ create_file error: {path} - {e}")
        return {"error": f"Failed to create file: {str(e)}"}


@tool
def modify_file(path: str, content: str) -> Dict[str, Any]:
    """
    Modify an existing file with new content.
    
    Automatically creates backup before modifying.
    
    Args:
        path: File path relative to workspace
        content: New file content
        
    Returns:
        Dictionary with success status and backup info
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"File not found: {path}"}
    
    try:
        # ALWAYS create backup before modifying
        backup_id = None
        if _backup_manager:
            backup_id = _backup_manager.create_backup(full_path, "modify")
        
        # Write new content
        full_path.write_text(content, encoding="utf-8")
        
        result = {
            "success": True,
            "path": path,
            "lines": len(content.split("\n")),
            "size_bytes": len(content.encode("utf-8"))
        }
        
        if backup_id:
            result["backup_id"] = backup_id
            result["backup_message"] = "✅ Backup created automatically"
        
        return result
    except Exception as e:
        return {"error": f"Failed to modify file: {str(e)}"}


@tool
def patch_file(path: str, find_text: str, replace_text: str, occurrence: int = 1) -> Dict[str, Any]:
    """
    Patch a file by finding and replacing specific text.
    
    Use this for TARGETED edits when you only need to change a specific section
    without rewriting the entire file. For example, updating a checkbox from [ ] to [x].
    
    Automatically creates backup before patching.
    
    Args:
        path: File path relative to workspace
        find_text: Exact text to find (including whitespace and newlines)
        replace_text: Text to replace it with
        occurrence: Which occurrence to replace (1=first, 0=all occurrences)
        
    Returns:
        Dictionary with success status and number of replacements made
    """
    agent_logger.info(f"🔧 Tool: patch_file({path}, find={find_text[:50]}..., replace={replace_text[:50]}...)")
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"File not found: {path}"}
    
    try:
        content = full_path.read_text(encoding="utf-8")
        
        # Check if the text exists
        if find_text not in content:
            return {
                "error": f"Text not found in file",
                "hint": "The exact text was not found. Check for extra spaces, newlines, or typos."
            }
        
        # Count occurrences
        count = content.count(find_text)
        
        if occurrence == 0:
            # Replace all occurrences
            new_content = content.replace(find_text, replace_text)
            replaced_count = count
        else:
            # Replace specific occurrence
            if occurrence > count:
                return {"error": f"Only {count} occurrence(s) found, requested occurrence {occurrence}"}
            
            # Find the nth occurrence and replace it
            idx = -1
            for i in range(occurrence):
                idx = content.find(find_text, idx + 1)
            
            new_content = content[:idx] + replace_text + content[idx + len(find_text):]
            replaced_count = 1
        
        # ALWAYS create backup before patching
        backup_id = None
        if _backup_manager:
            backup_id = _backup_manager.create_backup(full_path, "patch")
        
        # Write back
        full_path.write_text(new_content, encoding="utf-8")
        
        agent_logger.info(f"✅ patch_file success: {path} ({replaced_count} replacement(s))")
        result = {
            "success": True,
            "path": path,
            "replacements": replaced_count,
            "occurrences_found": count
        }
        
        if backup_id:
            result["backup_id"] = backup_id
            result["backup_message"] = "✅ Backup created automatically"
        
        return result
        
    except Exception as e:
        agent_logger.error(f"❌ patch_file error: {path} - {e}")
        return {"error": f"Failed to patch file: {str(e)}"}


@tool
def delete_file(path: str, recursive: bool = False) -> Dict[str, Any]:
    """
    Delete a file or directory.
    
    Automatically creates backup before deleting.
    
    Args:
        path: File/directory path relative to workspace
        recursive: If True, delete directories recursively
        
    Returns:
        Dictionary with success status and backup info
    """
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"Path not found: {path}"}
    
    try:
        # ALWAYS create backup before deleting
        backup_id = None
        if _backup_manager and full_path.is_file():
            backup_id = _backup_manager.create_backup(full_path, "delete")
        
        if full_path.is_file():
            full_path.unlink()
            return {
                "success": True,
                "deleted": path,
                "type": "file",
                "backup_id": backup_id,
                "backup_message": "✅ Backup created - can be restored if needed" if backup_id else None
            }
        elif full_path.is_dir():
            if recursive:
                import shutil
                shutil.rmtree(full_path)
                return {
                    "success": True,
                    "deleted": path,
                    "type": "directory",
                    "backup_message": "⚠️ Directory deleted (no backup for directories)"
                }
            else:
                # Check if directory is empty
                if any(full_path.iterdir()):
                    return {"error": f"Directory not empty: {path}. Set recursive=True to delete."}
                full_path.rmdir()
                return {
                    "success": True,
                    "deleted": path,
                    "type": "directory"
                }
    except Exception as e:
        return {"error": f"Failed to delete: {str(e)}"}


@tool
def move_file(source: str, destination: str) -> Dict[str, Any]:
    """
    Move or rename a file/directory.
    
    Args:
        source: Source path relative to workspace
        destination: Destination path relative to workspace
        
    Returns:
        Dictionary with success status
    """
    agent_logger.info(f"🔧 Tool: move_file({source} -> {destination})")
    
    # Validate source
    is_valid, error, source_path = validate_path(source)
    if not is_valid:
        return {"error": f"Source: {error}"}
    
    if not source_path.exists():
        return {"error": f"Source not found: {source}"}
    
    # Validate destination
    is_valid, error, dest_path = validate_path(destination)
    if not is_valid:
        return {"error": f"Destination: {error}"}
    
    try:
        import shutil
        
        # Create destination directory if needed
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file/directory
        shutil.move(str(source_path), str(dest_path))
        
        agent_logger.info(f"✅ Moved: {source} -> {destination}")
        return {
            "success": True,
            "source": source,
            "destination": destination,
            "message": f"Moved {source} to {destination}"
        }
    except Exception as e:
        agent_logger.error(f"❌ Move failed: {e}")
        return {"error": f"Failed to move: {str(e)}"}


# ============================================================================
# Backup & Restore Tools
# ============================================================================

@tool
def restore_backup(backup_id: str) -> Dict[str, Any]:
    """
    Restore a file from backup.
    
    Use list_backups() to see available backups.
    
    Args:
        backup_id: Backup ID from list_backups()
        
    Returns:
        Success status
    """
    if not _backup_manager:
        return {"error": "Backup manager not initialized"}
    
    if _backup_manager.restore_backup(backup_id):
        return {
            "success": True,
            "message": f"✅ Restored backup {backup_id}",
            "backup_id": backup_id
        }
    else:
        return {"error": f"Backup {backup_id} not found or restore failed"}


@tool
def list_backups(file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    List available backups.
    
    Args:
        file_path: Optional - filter by specific file
        
    Returns:
        List of backups with timestamps
    """
    if not _backup_manager:
        return {"error": "Backup manager not initialized"}
    
    backups = _backup_manager.list_backups(file_path)
    
    return {
        "backups": backups,
        "total": len(backups),
        "message": "Use restore_backup(backup_id) to restore a backup"
    }


@tool
def show_diff(path: str, backup_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Show differences between current file and backup.
    
    Args:
        path: File path
        backup_id: Optional backup ID (defaults to most recent)
        
    Returns:
        Diff in unified format
    """
    if not _backup_manager:
        return {"error": "Backup manager not initialized"}
    
    is_valid, error, full_path = validate_path(path)
    if not is_valid:
        return {"error": error}
    
    # Get backup
    if backup_id:
        backup_info = next((b for b in _backup_manager.index["backups"] if b["id"] == backup_id), None)
        if not backup_info:
            return {"error": f"Backup {backup_id} not found"}
    else:
        backup_info = _backup_manager.get_last_backup(path)
        if not backup_info:
            return {"error": f"No backups found for {path}"}
        backup_id = backup_info["id"]
    
    # Read both versions
    old_content = _backup_manager.get_backup_content(backup_id)
    if old_content is None:
        return {"error": f"Could not read backup {backup_id}"}
    
    if full_path.exists():
        try:
            new_content = full_path.read_text(encoding='utf-8')
        except Exception as e:
            return {"error": f"Could not read current file: {str(e)}"}
    else:
        new_content = "[FILE DELETED]"
    
    # Generate diff (simple line-by-line)
    import difflib
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"{path} (backup {backup_info['timestamp']})",
        tofile=f"{path} (current)",
        lineterm=''
    )
    
    diff_text = ''.join(diff)
    
    if not diff_text:
        diff_text = "No differences found"
    
    return {
        "path": path,
        "backup_id": backup_id,
        "backup_timestamp": backup_info["timestamp"],
        "diff": diff_text,
        "lines_changed": diff_text.count('\n')
    }


# Export file operation tools only (search tools are in search_tools.py)
FILE_TOOLS = [
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
]

