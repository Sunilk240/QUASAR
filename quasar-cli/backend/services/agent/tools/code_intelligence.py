"""
Code Intelligence Tools for AI Agent

Provides code analysis tools without requiring external LSP servers.
Uses static analysis with Python's ast module and regex patterns.

For full LSP support, integrate with editor's LSP server in future.
"""

import ast
import re
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from langchain_core.tools import tool

from ..logger import agent_logger


def _get_workspace() -> Path:
    """Get current workspace path."""
    from .file_tools import get_workspace
    return get_workspace()


def _validate_path(path: str) -> tuple[bool, str, Optional[Path]]:
    """Validate path is within workspace."""
    from .file_tools import validate_path
    return validate_path(path)


def _read_file_content(file_path: Path) -> Optional[str]:
    """Read file content safely."""
    try:
        return file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        return None


@tool
def get_diagnostics(path: str) -> Dict[str, Any]:
    """
    Get syntax errors and warnings from a Python file.
    
    Uses Python's ast module to detect syntax errors.
    For non-Python files, returns basic line-based analysis.
    
    Args:
        path: File path to analyze
        
    Returns:
        Dictionary with diagnostics (errors, warnings)
    """
    agent_logger.info(f"🔍 Tool: get_diagnostics({path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"File not found: {path}"}
    
    content = _read_file_content(full_path)
    if content is None:
        return {"error": f"Could not read file: {path}"}
    
    diagnostics = {
        "file": path,
        "errors": [],
        "warnings": [],
        "info": []
    }
    
    # Python files - use ast
    if path.endswith('.py'):
        try:
            ast.parse(content)
        except SyntaxError as e:
            diagnostics["errors"].append({
                "line": e.lineno or 1,
                "column": e.offset or 0,
                "message": str(e.msg),
                "severity": "error"
            })
        
        # Check for common issues
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Unused imports detection (simple)
            if line.strip().startswith('import ') or ' import ' in line:
                # Check if imported name is used
                if 'import *' in line:
                    diagnostics["warnings"].append({
                        "line": i,
                        "message": "Avoid 'import *' - makes code harder to understand",
                        "severity": "warning"
                    })
            
            # Long lines
            if len(line) > 120:
                diagnostics["info"].append({
                    "line": i,
                    "message": f"Line exceeds 120 characters ({len(line)} chars)",
                    "severity": "info"
                })
            
            # TODO comments
            if 'TODO' in line or 'FIXME' in line or 'HACK' in line:
                diagnostics["info"].append({
                    "line": i,
                    "message": f"Found TODO/FIXME comment",
                    "severity": "info"
                })
    
    # JavaScript/TypeScript - basic checks
    elif path.endswith(('.js', '.ts', '.jsx', '.tsx')):
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Console.log detection
            if 'console.log' in line and not line.strip().startswith('//'):
                diagnostics["warnings"].append({
                    "line": i,
                    "message": "Consider removing console.log for production",
                    "severity": "warning"
                })
            
            # var usage
            if re.match(r'^\s*var\s+', line):
                diagnostics["info"].append({
                    "line": i,
                    "message": "Consider using 'let' or 'const' instead of 'var'",
                    "severity": "info"
                })
    
    diagnostics["total_issues"] = (
        len(diagnostics["errors"]) + 
        len(diagnostics["warnings"]) + 
        len(diagnostics["info"])
    )
    
    return diagnostics


@tool
def get_symbols(path: str) -> Dict[str, Any]:
    """
    List all symbols (functions, classes, variables) in a file.
    
    Provides a quick overview of file structure.
    
    Args:
        path: File path to analyze
        
    Returns:
        Dictionary with symbols organized by type
    """
    agent_logger.info(f"🔍 Tool: get_symbols({path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    if not full_path.exists():
        return {"error": f"File not found: {path}"}
    
    content = _read_file_content(full_path)
    if content is None:
        return {"error": f"Could not read file: {path}"}
    
    symbols = {
        "file": path,
        "classes": [],
        "functions": [],
        "variables": [],
        "imports": []
    }
    
    # Python files - use ast
    if path.endswith('.py'):
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    methods = [
                        n.name for n in node.body 
                        if isinstance(n, ast.FunctionDef)
                    ]
                    symbols["classes"].append({
                        "name": node.name,
                        "line": node.lineno,
                        "methods": methods[:10]  # Limit methods shown
                    })
                elif isinstance(node, ast.FunctionDef) and not isinstance(node, ast.AsyncFunctionDef):
                    # Only top-level functions
                    if hasattr(node, 'col_offset') and node.col_offset == 0:
                        symbols["functions"].append({
                            "name": node.name,
                            "line": node.lineno,
                            "args": [arg.arg for arg in node.args.args][:5]
                        })
                elif isinstance(node, ast.AsyncFunctionDef):
                    if hasattr(node, 'col_offset') and node.col_offset == 0:
                        symbols["functions"].append({
                            "name": f"async {node.name}",
                            "line": node.lineno,
                            "args": [arg.arg for arg in node.args.args][:5]
                        })
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            symbols["imports"].append({
                                "name": alias.name,
                                "line": node.lineno
                            })
                    else:
                        module = node.module or ""
                        for alias in node.names:
                            symbols["imports"].append({
                                "name": f"{module}.{alias.name}",
                                "line": node.lineno
                            })
        except SyntaxError:
            # Fall back to regex for files with syntax errors
            pass
    
    # JavaScript/TypeScript - regex based
    elif path.endswith(('.js', '.ts', '.jsx', '.tsx')):
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Function declarations
            match = re.match(r'^\s*(async\s+)?function\s+(\w+)', line)
            if match:
                symbols["functions"].append({
                    "name": match.group(2),
                    "line": i,
                    "async": bool(match.group(1))
                })
            
            # Arrow functions with names
            match = re.match(r'^\s*(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\(', line)
            if match:
                symbols["functions"].append({
                    "name": match.group(2),
                    "line": i,
                    "type": "arrow"
                })
            
            # Class declarations
            match = re.match(r'^\s*class\s+(\w+)', line)
            if match:
                symbols["classes"].append({
                    "name": match.group(1),
                    "line": i
                })
    
    symbols["total_symbols"] = (
        len(symbols["classes"]) + 
        len(symbols["functions"]) + 
        len(symbols["variables"]) +
        len(symbols["imports"])
    )
    
    return symbols


@tool
def find_definition(symbol: str, path: str = ".") -> Dict[str, Any]:
    """
    Find where a symbol (function, class, variable) is defined.
    
    Searches the specified path for definition of the symbol.
    
    Args:
        symbol: Name of the symbol to find
        path: File or directory to search in
        
    Returns:
        Dictionary with definition location(s)
    """
    agent_logger.info(f"🔍 Tool: find_definition({symbol}, {path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    definitions = []
    
    # Patterns for finding definitions
    patterns = {
        'python': [
            rf'^class\s+{re.escape(symbol)}\s*[:\(]',           # class Foo:
            rf'^def\s+{re.escape(symbol)}\s*\(',                # def foo(
            rf'^async\s+def\s+{re.escape(symbol)}\s*\(',        # async def foo(
            rf'^{re.escape(symbol)}\s*=',                       # foo = 
        ],
        'javascript': [
            rf'^class\s+{re.escape(symbol)}\s*[{{\s]',          # class Foo {
            rf'^function\s+{re.escape(symbol)}\s*\(',           # function foo(
            rf'^(const|let|var)\s+{re.escape(symbol)}\s*=',     # const foo =
            rf'^export\s+(default\s+)?(class|function)\s+{re.escape(symbol)}',
        ]
    }
    
    def search_file(file_path: Path):
        content = _read_file_content(file_path)
        if not content:
            return
        
        ext = file_path.suffix.lower()
        if ext == '.py':
            file_patterns = patterns['python']
        elif ext in ['.js', '.ts', '.jsx', '.tsx']:
            file_patterns = patterns['javascript']
        else:
            return
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            for pattern in file_patterns:
                if re.match(pattern, line.strip()):
                    rel_path = str(file_path.relative_to(_get_workspace()))
                    definitions.append({
                        "file": rel_path,
                        "line": i,
                        "content": line.strip()[:100]
                    })
                    return  # Found in this file
    
    if full_path.is_file():
        search_file(full_path)
    else:
        # Search directory
        for ext in ['.py', '.js', '.ts', '.jsx', '.tsx']:
            for file_path in full_path.rglob(f'*{ext}'):
                # Skip ignored directories
                if any(d in str(file_path) for d in ['.git', 'node_modules', '__pycache__', '.venv']):
                    continue
                search_file(file_path)
                if len(definitions) >= 10:  # Limit results
                    break
    
    return {
        "symbol": symbol,
        "definitions": definitions,
        "total_found": len(definitions)
    }


@tool
def find_references(symbol: str, path: str = ".") -> Dict[str, Any]:
    """
    Find all references to a symbol in the codebase.
    
    Searches for usages of the symbol, not just definitions.
    
    Args:
        symbol: Name of the symbol to find references for
        path: File or directory to search in
        
    Returns:
        Dictionary with reference locations
    """
    agent_logger.info(f"🔍 Tool: find_references({symbol}, {path})")
    
    is_valid, error, full_path = _validate_path(path)
    if not is_valid:
        return {"error": error}
    
    references = []
    
    def search_file(file_path: Path):
        content = _read_file_content(file_path)
        if not content:
            return
        
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            # Check if symbol appears (as word boundary)
            if re.search(rf'\b{re.escape(symbol)}\b', line):
                rel_path = str(file_path.relative_to(_get_workspace()))
                references.append({
                    "file": rel_path,
                    "line": i,
                    "content": line.strip()[:100]
                })
    
    search_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs']
    
    if full_path.is_file():
        search_file(full_path)
    else:
        for ext in search_extensions:
            for file_path in full_path.rglob(f'*{ext}'):
                # Skip ignored directories
                if any(d in str(file_path) for d in ['.git', 'node_modules', '__pycache__', '.venv']):
                    continue
                search_file(file_path)
                if len(references) >= 100:  # Limit results
                    break
    
    return {
        "symbol": symbol,
        "references": references[:50],  # Return max 50
        "total_found": len(references),
        "truncated": len(references) > 50
    }


# Export code intelligence tools
CODE_INTELLIGENCE_TOOLS = [
    get_diagnostics,
    get_symbols,
    find_definition,
    find_references
]
