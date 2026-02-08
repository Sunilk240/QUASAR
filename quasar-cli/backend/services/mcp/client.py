"""
MCP Client Implementation

Handles communication with MCP servers via JSON-RPC over stdio.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import subprocess
import json
import asyncio
import logging
import os

logger = logging.getLogger("mcp_client")


@dataclass
class MCPToolDefinition:
    """Tool definition from MCP server."""
    name: str
    description: str
    inputSchema: Dict[str, Any] = field(default_factory=dict)  # JSON Schema
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """Alias for inputSchema (compatibility)."""
        return self.inputSchema


class MCPServer:
    """Represents a connected MCP server."""
    
    def __init__(
        self, 
        name: str, 
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None
    ):
        self.name = name
        self.command = command
        self.env = env or {}
        self.cwd = cwd
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: List[MCPToolDefinition] = []
        self._request_id = 0
        self._connected = False
        
        logger.info(f"🔌 MCPServer '{name}' initialized with command: {' '.join(command)}")
    
    def _get_next_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id
    
    async def connect(self) -> bool:
        """
        Start MCP server process and initialize connection.
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            logger.info(f"🔌 Connecting to MCP server '{self.name}'...")
            
            # Prepare environment
            env = os.environ.copy()
            env.update(self.env)
            
            # Start process
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=self.cwd
            )
            
            # Initialize connection
            init_response = await self._send_request({
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "clientInfo": {
                        "name": "quasar-cli",
                        "version": "1.0.0"
                    }
                },
                "id": self._get_next_id()
            })
            
            if "error" in init_response:
                logger.error(f"❌ MCP server '{self.name}' initialization failed: {init_response['error']}")
                return False
            
            logger.info(f"✅ MCP server '{self.name}' initialized")
            
            # Get available tools
            tools_response = await self._send_request({
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": self._get_next_id()
            })
            
            if "error" in tools_response:
                logger.error(f"❌ Failed to get tools from '{self.name}': {tools_response['error']}")
                return False
            
            # Parse tools
            tools_data = tools_response.get("result", {}).get("tools", [])
            self.tools = [
                MCPToolDefinition(
                    name=t["name"],
                    description=t.get("description", ""),
                    inputSchema=t.get("inputSchema", {})
                )
                for t in tools_data
            ]
            
            logger.info(f"✅ Loaded {len(self.tools)} tools from '{self.name}': {[t.name for t in self.tools]}")
            
            self._connected = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MCP server '{self.name}': {e}")
            if self.process:
                self.process.terminate()
                self.process = None
            return False
    
    async def execute_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a tool on this MCP server.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        if not self._connected:
            return {"error": f"MCP server '{self.name}' not connected"}
        
        try:
            logger.info(f"🔧 Executing MCP tool '{tool_name}' on server '{self.name}'")
            logger.debug(f"   Arguments: {arguments}")
            
            response = await self._send_request({
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": self._get_next_id()
            })
            
            if "error" in response:
                logger.error(f"❌ Tool execution failed: {response['error']}")
                return {"error": response["error"].get("message", "Unknown error")}
            
            result = response.get("result", {})
            logger.info(f"✅ Tool '{tool_name}' completed successfully")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error executing tool '{tool_name}': {e}")
            return {"error": str(e)}
    
    async def _send_request(self, request: Dict) -> Dict:
        """
        Send JSON-RPC request to server.
        
        Args:
            request: JSON-RPC request object
            
        Returns:
            JSON-RPC response object
        """
        if not self.process or not self.process.stdin:
            raise RuntimeError(f"MCP server '{self.name}' process not available")
        
        try:
            # Send request
            request_str = json.dumps(request) + "\n"
            self.process.stdin.write(request_str.encode())
            await self.process.stdin.drain()
            
            logger.debug(f"📤 Sent to '{self.name}': {request_str.strip()}")
            
            # Read response
            response_line = await asyncio.wait_for(
                self.process.stdout.readline(),
                timeout=30.0  # 30 second timeout
            )
            
            if not response_line:
                raise RuntimeError("Empty response from MCP server")
            
            response = json.loads(response_line.decode())
            logger.debug(f"📥 Received from '{self.name}': {json.dumps(response)[:200]}...")
            
            return response
            
        except asyncio.TimeoutError:
            logger.error(f"⏱️ Timeout waiting for response from '{self.name}'")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"❌ Invalid JSON response from '{self.name}': {e}")
            raise
    
    async def disconnect(self):
        """Stop MCP server and cleanup."""
        if self.process:
            logger.info(f"🔌 Disconnecting from MCP server '{self.name}'...")
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Force killing MCP server '{self.name}'")
                self.process.kill()
            finally:
                self.process = None
                self._connected = False
                logger.info(f"✅ Disconnected from '{self.name}'")
    
    @property
    def is_connected(self) -> bool:
        """Check if server is connected."""
        return self._connected and self.process is not None


class MCPManager:
    """Manages multiple MCP servers."""
    
    def __init__(self, workspace_path: Optional[Path] = None):
        """
        Initialize MCP manager.
        
        Args:
            workspace_path: Path to workspace directory (looks for .quasar/mcp.json)
        """
        # Look for config in project's .quasar/ directory (portable)
        if workspace_path:
            self.config_path = Path(workspace_path) / ".quasar" / "mcp.json"
        else:
            # Fallback to current directory
            self.config_path = Path.cwd() / ".quasar" / "mcp.json"
        
        self.servers: Dict[str, MCPServer] = {}
        
        logger.info(f"🔌 MCPManager initialized with config: {self.config_path}")
    
    async def load_servers(self) -> int:
        """
        Load and connect to configured MCP servers.
        
        Returns:
            Number of successfully connected servers
        """
        if not self.config_path.exists():
            logger.info(f"ℹ️ No MCP config found at {self.config_path}")
            return 0
        
        try:
            config = json.loads(self.config_path.read_text())
            logger.info(f"📋 Loading MCP servers from config...")
            
            servers_config = config.get("mcpServers", config.get("servers", []))
            
            # Handle both array and object formats
            if isinstance(servers_config, dict):
                # Object format: {"server_name": {...}}
                # Skip entries that aren't dicts (like "_comment": "string")
                servers_list = [
                    {"name": name, **server_config}
                    for name, server_config in servers_config.items()
                    if isinstance(server_config, dict)  # Skip non-dict entries
                ]
            else:
                # Array format: [{"name": "...", ...}]
                servers_list = servers_config
            
            connected_count = 0
            
            for server_config in servers_list:
                name = server_config.get("name")
                if not name:
                    logger.warning("⚠️ Skipping server config without name")
                    continue
                
                # Check if disabled
                if server_config.get("disabled", False):
                    logger.info(f"⏭️ Skipping disabled server '{name}'")
                    continue
                
                command = server_config.get("command", [])
                if isinstance(command, str):
                    command = [command]
                
                env = server_config.get("env", {})
                cwd = server_config.get("cwd")
                
                # Create and connect server
                server = MCPServer(name, command, env=env, cwd=cwd)
                
                if await server.connect():
                    self.servers[name] = server
                    connected_count += 1
                else:
                    logger.warning(f"⚠️ Failed to connect to server '{name}'")
            
            logger.info(f"✅ Connected to {connected_count}/{len(servers_list)} MCP servers")
            return connected_count
            
        except Exception as e:
            logger.error(f"❌ Error loading MCP servers: {e}")
            return 0
    
    def get_all_tools(self) -> List[MCPToolDefinition]:
        """
        Get tools from all connected servers.
        
        Returns:
            List of all available MCP tools (namespaced by server)
        """
        tools = []
        for server_name, server in self.servers.items():
            if server.is_connected:
                for tool in server.tools:
                    # Create namespaced tool
                    namespaced_tool = MCPToolDefinition(
                        name=f"{server_name}/{tool.name}",
                        description=f"[{server_name}] {tool.description}",
                        inputSchema=tool.inputSchema
                    )
                    tools.append(namespaced_tool)
        
        logger.info(f"📋 Total MCP tools available: {len(tools)}")
        return tools
    
    async def execute_tool(
        self, 
        namespaced_tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a namespaced MCP tool.
        
        Args:
            namespaced_tool_name: Tool name in format "server_name/tool_name"
            arguments: Tool arguments
            
        Returns:
            Tool execution result
        """
        # Parse server and tool name
        if "/" not in namespaced_tool_name:
            return {"error": f"Invalid MCP tool name: {namespaced_tool_name}. Expected format: server/tool"}
        
        server_name, tool_name = namespaced_tool_name.split("/", 1)
        
        # Get server
        server = self.servers.get(server_name)
        if not server:
            return {"error": f"MCP server '{server_name}' not found"}
        
        if not server.is_connected:
            return {"error": f"MCP server '{server_name}' not connected"}
        
        # Execute tool
        return await server.execute_tool(tool_name, arguments)
    
    async def disconnect_all(self):
        """Disconnect from all MCP servers."""
        logger.info("🔌 Disconnecting from all MCP servers...")
        
        for server in self.servers.values():
            await server.disconnect()
        
        self.servers.clear()
        logger.info("✅ All MCP servers disconnected")
    
    def get_server(self, name: str) -> Optional[MCPServer]:
        """Get a server by name."""
        return self.servers.get(name)
    
    @property
    def connected_servers(self) -> List[str]:
        """Get list of connected server names."""
        return [name for name, server in self.servers.items() if server.is_connected]
