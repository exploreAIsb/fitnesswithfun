"""MCP client wrapper to use Kaggle MCP server tools with ADK."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

LOGGER = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
MCP_SERVER_SCRIPT = BASE_DIR / "kaggle_mcp_server.py"


def _clean_json_result(data: Any) -> Any:
    """
    Clean data structure to remove NaN, None, and other non-JSON-serializable values.
    
    Args:
        data: Data structure to clean
        
    Returns:
        Cleaned data structure
    """
    import math
    
    if isinstance(data, dict):
        return {k: _clean_json_result(v) for k, v in data.items() if v is not None and not (isinstance(v, float) and math.isnan(v))}
    elif isinstance(data, list):
        return [_clean_json_result(item) for item in data if item is not None and not (isinstance(item, float) and math.isnan(item))]
    elif isinstance(data, float) and math.isnan(data):
        return None
    else:
        return data


async def call_kaggle_mcp_tool(
    tool_name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Call a tool from the Kaggle MCP server.
    
    Args:
        tool_name: Name of the MCP tool to call
        arguments: Arguments to pass to the tool
        
    Returns:
        Result from the MCP tool
    """
    server_params = StdioServerParameters(
        command="python",
        args=[str(MCP_SERVER_SCRIPT)],
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            
            # Find the requested tool
            tool = next((t for t in tools.tools if t.name == tool_name), None)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found in MCP server")
            
            # Call the tool
            try:
                result = await session.call_tool(tool_name, arguments)
                if result.content and len(result.content) > 0:
                    content = result.content[0]
                    if hasattr(content, "text"):
                        try:
                            return json.loads(content.text)
                        except json.JSONDecodeError:
                            return {"result": content.text}
                    elif hasattr(content, "json"):
                        return content.json
                return {}
            except Exception as e:
                LOGGER.error(f"Error calling MCP tool '{tool_name}': {e}")
                raise


def suggest_workout_plan_via_mcp(
    age: Optional[int] = None,
    daily_goal: Optional[str] = None,
    intensity: Optional[str] = None,
    mood: Optional[str] = None,
    restrictions: Optional[str] = None,
    exercise_minutes: Optional[int] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    ADK-compatible tool that uses MCP server to query Kaggle dataset.
    
    This is a synchronous wrapper around the async MCP client.
    Uses the Kaggle gym exercise dataset (niharika41298/gym-exercise-data) via MCP server.
    """
    LOGGER.info(f"suggest_workout_plan_via_mcp called with: age={age}, daily_goal={daily_goal}, intensity={intensity}, mood={mood}, restrictions={restrictions}, exercise_minutes={exercise_minutes}, limit={limit}")
    
    arguments = {
        "age": age,
        "daily_goal": daily_goal,
        "intensity": intensity,
        "mood": mood,
        "restrictions": restrictions,
        "exercise_minutes": exercise_minutes,
        "limit": limit,
    }
    # Remove None values
    arguments = {k: v for k, v in arguments.items() if v is not None}
    LOGGER.info(f"Calling MCP tool with arguments: {arguments}")
    
    try:
        # Check if we're in an async context (running event loop)
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, need to use a different approach
            # Create a new event loop in a thread
            import concurrent.futures
            import threading
            
            def run_in_thread():
                # Create a new event loop for this thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(call_kaggle_mcp_tool("search_exercises", arguments))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                result = future.result(timeout=30)  # 30 second timeout
        except RuntimeError:
            # No running event loop, safe to use asyncio.run()
            result = asyncio.run(call_kaggle_mcp_tool("search_exercises", arguments))
        
        # Clean the result to handle NaN and other non-serializable values
        result = _clean_json_result(result)
        LOGGER.info(f"MCP tool returned result with keys: {list(result.keys()) if isinstance(result, dict) else 'not a dict'}")
        
        if isinstance(result, str):
            return json.loads(result)
        return result
    except Exception as e:
        error_msg = f"Failed to query Kaggle dataset via MCP: {e}"
        LOGGER.exception(f"Exception in suggest_workout_plan_via_mcp: {e}")
        return {
            "error": error_msg,
            "exercises": [],
            "count": 0,
            "filters_applied": arguments,
        }


if __name__ == "__main__":
    # Test the MCP client
    result = suggest_workout_plan_via_mcp(intensity="moderate", limit=5)
    print(result)

