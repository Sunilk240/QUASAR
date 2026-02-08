"""
MCP (Model Context Protocol) Client Package

Enables external tool servers to extend QUASAR capabilities.
Implements the Model Context Protocol for connecting to external tool providers.
"""

from .client import MCPManager, MCPServer, MCPToolDefinition
from .adapter import MCPToolAdapter

__all__ = [
    "MCPManager",
    "MCPServer", 
    "MCPToolDefinition",
    "MCPToolAdapter",
]
