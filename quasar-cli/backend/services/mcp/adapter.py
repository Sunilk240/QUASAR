"""
MCP Tool Adapter

Converts MCP tools to LangChain-compatible tools.
"""

from typing import Dict, Any, Optional
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model
import logging

from .client import MCPManager, MCPToolDefinition

logger = logging.getLogger("mcp_adapter")


class MCPToolAdapter(BaseTool):
    """
    Adapter that wraps an MCP tool as a LangChain tool.
    
    This allows MCP tools to be used seamlessly in the agentic loop
    alongside native QUASAR tools.
    """
    
    name: str
    description: str
    mcp_manager: MCPManager
    mcp_tool_name: str  # Namespaced name (server/tool)
    args_schema: Optional[type[BaseModel]] = None
    
    def __init__(
        self,
        mcp_tool: MCPToolDefinition,
        mcp_manager: MCPManager,
        **kwargs
    ):
        """
        Initialize MCP tool adapter.
        
        Args:
            mcp_tool: MCP tool definition
            mcp_manager: MCP manager instance for execution
        """
        # Create Pydantic model from JSON Schema
        args_schema = self._create_args_schema(mcp_tool)
        
        super().__init__(
            name=mcp_tool.name,
            description=mcp_tool.description,
            mcp_manager=mcp_manager,
            mcp_tool_name=mcp_tool.name,
            args_schema=args_schema,
            **kwargs
        )
        
        logger.debug(f"🔧 Created adapter for MCP tool: {mcp_tool.name}")
    
    def _create_args_schema(self, mcp_tool: MCPToolDefinition) -> type[BaseModel]:
        """
        Create Pydantic model from JSON Schema.
        
        Args:
            mcp_tool: MCP tool definition
            
        Returns:
            Pydantic model class
        """
        input_schema = mcp_tool.inputSchema
        
        if not input_schema or not input_schema.get("properties"):
            # No schema - create empty model
            return create_model(
                f"{mcp_tool.name}_Args",
                __base__=BaseModel
            )
        
        # Extract properties and required fields
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        
        # Build field definitions
        fields = {}
        for prop_name, prop_schema in properties.items():
            prop_type = self._json_type_to_python(prop_schema.get("type", "string"))
            prop_description = prop_schema.get("description", "")
            prop_default = ... if prop_name in required else None
            
            fields[prop_name] = (
                prop_type,
                Field(default=prop_default, description=prop_description)
            )
        
        # Create dynamic Pydantic model
        model = create_model(
            f"{mcp_tool.name.replace('/', '_')}_Args",
            __base__=BaseModel,
            **fields
        )
        
        return model
    
    def _json_type_to_python(self, json_type: str) -> type:
        """Convert JSON Schema type to Python type."""
        type_map = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return type_map.get(json_type, str)
    
    def _run(self, **kwargs) -> str:
        """Synchronous execution (not supported for MCP)."""
        raise NotImplementedError("MCP tools only support async execution")
    
    async def _arun(self, **kwargs) -> str:
        """
        Execute the MCP tool asynchronously.
        
        Args:
            **kwargs: Tool arguments
            
        Returns:
            Tool execution result as string
        """
        try:
            logger.info(f"🔧 Executing MCP tool: {self.mcp_tool_name}")
            logger.debug(f"   Arguments: {kwargs}")
            
            # Execute via MCP manager
            result = await self.mcp_manager.execute_tool(
                self.mcp_tool_name,
                kwargs
            )
            
            # Format result
            if "error" in result:
                error_msg = result["error"]
                logger.error(f"❌ MCP tool error: {error_msg}")
                return f"Error: {error_msg}"
            
            # Extract content from result
            content = result.get("content", [])
            
            if not content:
                return "Tool executed successfully (no output)"
            
            # Format content based on type
            formatted_parts = []
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "text")
                    
                    if item_type == "text":
                        formatted_parts.append(item.get("text", ""))
                    elif item_type == "resource":
                        # Resource reference
                        uri = item.get("resource", {}).get("uri", "")
                        formatted_parts.append(f"Resource: {uri}")
                    else:
                        # Unknown type - stringify
                        formatted_parts.append(str(item))
                else:
                    formatted_parts.append(str(item))
            
            result_str = "\n".join(formatted_parts)
            logger.info(f"✅ MCP tool completed: {len(result_str)} chars")
            
            return result_str
            
        except Exception as e:
            logger.error(f"❌ Error executing MCP tool '{self.mcp_tool_name}': {e}")
            return f"Error executing MCP tool: {str(e)}"


def create_mcp_tools(mcp_manager: MCPManager) -> list[BaseTool]:
    """
    Create LangChain tools from all available MCP tools.
    
    Args:
        mcp_manager: MCP manager with connected servers
        
    Returns:
        List of LangChain-compatible tools
    """
    mcp_tools = mcp_manager.get_all_tools()
    
    langchain_tools = []
    for mcp_tool in mcp_tools:
        try:
            adapter = MCPToolAdapter(mcp_tool, mcp_manager)
            langchain_tools.append(adapter)
        except Exception as e:
            logger.error(f"❌ Failed to create adapter for '{mcp_tool.name}': {e}")
    
    logger.info(f"✅ Created {len(langchain_tools)} LangChain tools from MCP")
    return langchain_tools
