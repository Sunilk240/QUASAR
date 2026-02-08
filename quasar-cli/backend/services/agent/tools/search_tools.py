"""
Search Tools for AI Agent

OS-native search tools optimized for Windows (primary) with cross-platform fallback.
Tool naming follows Claude Code conventions for clarity.
"""

import subprocess
import platform
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
from langchain_core.tools import tool

from ..logger import agent_logger

# OS Detection at module load
IS_WINDOWS = platform.system() == "Windows"

# Ignored directories (performance + relevance)
IGNORED_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", 
    ".editor", "dist", "build", ".cache", ".next", ".nuxt"
}


def _get_workspace() -> Path:
    """Get current workspace path."""
    from .file_tools import get_workspace
    return get_workspace()


def _validate_path(path: str) -> tuple[bool, str, Optional[Path]]:
    """Validate path is within workspace."""
    from .file_tools import validate_path
    return validate_path(path)


def _should_ignore(path: str) -> bool:
    """Check if path should be ignored."""
    return any(d in path for d in IGNORED_DIRS)


@tool
def find_files(pattern: str, path: str = ".", max_results: int = 50) -> Dict[str, Any]:
    """
    Find files by name pattern in the workspace.
    
    Use this to locate files when you know part of the filename.
    Supports glob patterns like *.py, test_*, etc.
    
    Args:
        pattern: File name pattern (e.g., "*.py", "test_*.js", "config*")
        path: Directory to search in (default: workspace root)
        max_results: Maximum number of results to return
        
    Returns:
        Dictionary with matching file paths
    """
    agent_logger.info(f"🔍 Tool: find_files({pattern}, {path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    matches = []
    
    try:
        if IS_WINDOWS:
            # Windows: Use dir /S /B for fast recursive listing
            cmd = ["cmd", "/c", f"dir /S /B {pattern}"]
            process = subprocess.run(
                cmd, 
                cwd=full_path, 
                capture_output=True, 
                text=True, 
                encoding="cp437", 
                errors="ignore"
            )
            
            for line in process.stdout.splitlines():
                if line.strip() and not _should_ignore(line):
                    # Convert to relative path
                    try:
                        rel = os.path.relpath(line.strip(), full_path)
                        matches.append(rel)
                    except:
                        pass
        else:
            # Unix: Use find command
            cmd = ["find", ".", "-name", pattern, "-type", "f"]
            process = subprocess.run(
                cmd, 
                cwd=full_path, 
                capture_output=True, 
                text=True
            )
            
            for line in process.stdout.splitlines():
                if line.strip() and not _should_ignore(line):
                    matches.append(line.strip().lstrip("./"))
        
        # Fallback: Python glob if native fails
        if not matches:
            import fnmatch
            for root, dirs, files in os.walk(full_path):
                # Skip ignored directories
                dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
                
                for file in files:
                    if fnmatch.fnmatch(file, pattern):
                        rel = os.path.relpath(os.path.join(root, file), full_path)
                        matches.append(rel)
                        if len(matches) >= max_results:
                            break
                if len(matches) >= max_results:
                    break
        
        return {
            "pattern": pattern,
            "matches": matches[:max_results],
            "total_found": len(matches),
            "truncated": len(matches) > max_results
        }
        
    except Exception as e:
        agent_logger.error(f"❌ find_files error: {e}")
        return {"error": f"Find files failed: {str(e)}"}


@tool
def search_content(query: str, path: str = ".", file_pattern: str = None) -> Dict[str, Any]:
    """
    Search for text content inside files.
    
    Use this to find code, strings, or patterns within files.
    Windows uses findstr, Unix uses grep/rg if available.
    
    Args:
        query: Text or pattern to search for
        path: Directory to search in (default: workspace root)
        file_pattern: Optional file filter (e.g., "*.py", "*.js")
        
    Returns:
        Dictionary with matches including file, line number, and content
    """
    agent_logger.info(f"🔍 Tool: search_content({query[:30]}..., {path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    matches = []
    
    try:
        if IS_WINDOWS:
            # Windows: Use findstr for speed
            # /S = recursive, /N = line numbers
            cmd = ["findstr", "/S", "/N", query]
            
            if file_pattern:
                cmd.append(file_pattern)
            else:
                cmd.append("*.*")
            
            process = subprocess.run(
                cmd,
                cwd=full_path,
                capture_output=True,
                text=True,
                encoding="cp437",
                errors="ignore"
            )
            
            for line in process.stdout.splitlines():
                if ":" in line:
                    try:
                        # findstr format: file:line:content
                        parts = line.split(":", 2)
                        if len(parts) >= 3:
                            file_path = parts[0]
                            
                            # Skip ignored directories
                            if _should_ignore(file_path):
                                continue
                            
                            matches.append({
                                "file": file_path,
                                "line": int(parts[1]),
                                "content": parts[2].strip()[:200]  # Limit content length
                            })
                    except:
                        continue
        else:
            # Unix: Try ripgrep first, fallback to grep
            rg_available = subprocess.run(
                ["which", "rg"], 
                capture_output=True
            ).returncode == 0
            
            if rg_available:
                cmd = ["rg", "--no-heading", "-n", query]
                if file_pattern:
                    cmd.extend(["-g", file_pattern])
            else:
                cmd = ["grep", "-rn", query, "."]
                if file_pattern:
                    cmd.extend(["--include", file_pattern])
            
            process = subprocess.run(
                cmd,
                cwd=full_path,
                capture_output=True,
                text=True
            )
            
            for line in process.stdout.splitlines():
                if ":" in line:
                    try:
                        parts = line.split(":", 2)
                        if len(parts) >= 3 and not _should_ignore(parts[0]):
                            matches.append({
                                "file": parts[0].lstrip("./"),
                                "line": int(parts[1]),
                                "content": parts[2].strip()[:200]
                            })
                    except:
                        continue
        
        return {
            "query": query,
            "matches": matches[:100],  # Limit for context safety
            "total_matches": len(matches),
            "truncated": len(matches) > 100
        }
        
    except Exception as e:
        agent_logger.error(f"❌ search_content error: {e}")
        return {"error": f"Search content failed: {str(e)}"}


@tool
def explore_codebase(path: str = ".", depth: int = 3) -> Dict[str, Any]:
    """
    Get a quick overview of project structure.
    
    Use this when starting work on a new codebase to understand its layout.
    Returns directory tree with file counts and key file detection.
    
    Args:
        path: Directory to explore (default: workspace root)
        depth: How deep to explore (default: 3 levels)
        
    Returns:
        Dictionary with tree structure and summary
    """
    agent_logger.info(f"🔍 Tool: explore_codebase({path}, depth={depth})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    tree = []
    file_types = {}
    key_files = []
    
    # Key files to detect
    KEY_FILE_NAMES = {
        "package.json", "requirements.txt", "pyproject.toml", "Cargo.toml",
        "go.mod", "pom.xml", "build.gradle", "Makefile", "CMakeLists.txt",
        "README.md", "README", ".gitignore", "Dockerfile", "docker-compose.yml"
    }
    
    def scan_dir(dir_path: Path, current_depth: int, prefix: str = ""):
        if current_depth > depth:
            return
        
        try:
            entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            return
        
        for i, entry in enumerate(entries):
            if entry.name in IGNORED_DIRS:
                continue
            
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            
            if entry.is_dir():
                tree.append(f"{prefix}{connector}{entry.name}/")
                new_prefix = prefix + ("    " if is_last else "│   ")
                scan_dir(entry, current_depth + 1, new_prefix)
            else:
                tree.append(f"{prefix}{connector}{entry.name}")
                
                # Track file types
                ext = entry.suffix.lower() or "(no extension)"
                file_types[ext] = file_types.get(ext, 0) + 1
                
                # Detect key files
                if entry.name in KEY_FILE_NAMES:
                    key_files.append(str(entry.relative_to(full_path)))
    
    try:
        tree.append(f"{full_path.name}/")
        scan_dir(full_path, 0)
        
        # Sort file types by count
        sorted_types = sorted(file_types.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "tree": "\n".join(tree[:100]),  # Limit tree output
            "tree_truncated": len(tree) > 100,
            "file_types": dict(sorted_types),
            "key_files": key_files,
            "total_items": len(tree)
        }
        
    except Exception as e:
        agent_logger.error(f"❌ explore_codebase error: {e}")
        return {"error": f"Explore codebase failed: {str(e)}"}


@tool  
def list_directory(path: str = ".", show_hidden: bool = False) -> Dict[str, Any]:
    """
    List files and directories in a path.
    
    Simple directory listing for quick navigation.
    
    Args:
        path: Directory to list (default: workspace root)
        show_hidden: Include hidden files (starting with .)
        
    Returns:
        Dictionary with files and directories
    """
    agent_logger.info(f"🔍 Tool: list_directory({path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.is_dir():
        return {"error": f"Not a directory: {path}"}
    
    try:
        files = []
        directories = []
        
        for entry in sorted(full_path.iterdir(), key=lambda x: x.name.lower()):
            name = entry.name
            
            # Skip hidden unless requested
            if not show_hidden and name.startswith("."):
                continue
            
            # Skip ignored
            if name in IGNORED_DIRS:
                continue
            
            if entry.is_dir():
                directories.append(name + "/")
            else:
                size = entry.stat().st_size
                files.append({
                    "name": name,
                    "size": size,
                    "size_human": _human_size(size)
                })
        
        return {
            "path": path,
            "directories": directories,
            "files": files,
            "total": len(directories) + len(files)
        }
        
    except Exception as e:
        agent_logger.error(f"❌ list_directory error: {e}")
        return {"error": f"List directory failed: {str(e)}"}


def _human_size(size: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}" if unit != "B" else f"{size}B"
        size /= 1024
    return f"{size:.1f}TB"


# Export search tools with new names
SEARCH_TOOLS = [
    find_files,
    search_content,
    explore_codebase,
    list_directory
]
