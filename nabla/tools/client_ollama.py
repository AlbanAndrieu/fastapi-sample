# client_ollama.py
import asyncio
import json
import os
import sys

import ollama
from fastmcp import Client as MCPClient

# Default model if DEFAULT_MODEL is unset or empty
OLLAMA_MODEL = (os.getenv("DEFAULT_MODEL") or "").strip() or "bonsai-2:9b"
# Same num_ctx as the workstation LiteLLM "qwen" route, or ollama reloads the model on the 6 GB GPU.
OLLAMA_OPTIONS = {"num_ctx": 32768}

MCP_SERVER_URL = "http://127.0.0.1:8091/llm/mcp/"

def chat_with_model(messages, *, tools=None, temperature=None):
    """Apply consistent GPU context and thinking options to each Ollama turn."""
    options = OLLAMA_OPTIONS.copy()
    if temperature is not None:
        options["temperature"] = temperature

    kwargs = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "think": False,
        "options": options,
        "stream": False,
    }
    if tools is not None:
        kwargs["tools"] = tools
    return ollama.chat(**kwargs)


# ------------------------------------------------------------
# Step 1: Discover available tools from MCP server
# ------------------------------------------------------------
async def load_mcp_tools():
    """Connect to MCP server and get list of available tools"""
    try:
        async with MCPClient(MCP_SERVER_URL) as mcp:
            # Ask server: "What tools do you have?"
            tools_list = await mcp.list_tools()

            # Convert to format Ollama understands
            ollama_tools = []
            for tool in tools_list:
                ollama_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.inputSchema,
                        },
                    },
                )
            return ollama_tools
    except Exception as e:
        print(f"❌ ERROR connecting to MCP server: {e}")
        print("\nMake sure the server is running:")
        print(" uv run python mcp_server.py")
        sys.exit(1)


# ------------------------------------------------------------
# Step 2: Execute a tool when AI requests it
# ------------------------------------------------------------
async def execute_tool(tool_name: str, arguments: dict):
    """Call a tool on the MCP server with given arguments"""
    try:
        async with MCPClient(MCP_SERVER_URL) as mcp:
            result = await mcp.call_tool(tool_name, arguments)
            return result
    except Exception as e:
        print(f"❌ ERROR executing tool {tool_name}: {e}")
        return {"error": str(e)}


# ------------------------------------------------------------
# Step 3: Main conversation loop
# ------------------------------------------------------------
async def main():
    print("🔍 Loading MCP tools...")
    tools = await load_mcp_tools()
    print(f"✅ Loaded {len(tools)} tools:")
    for tool in tools:
        print(f"   - {tool['function']['name']}: {tool['function']['description']}")
    print()

    # The user's question
    user_msg = "Please greet Alban and then add 150 + 75."
    print(f"👤 User question: {user_msg}\n")

    # Send to Ollama with tools available
    try:
        response = chat_with_model(
            [{"role": "user", "content": user_msg}],
            tools=tools,
        )
    except Exception as e:
        print(f"❌ ERROR calling Ollama: {e}")
        print("\nMake sure:")
        print("  1. Ollama is running (ollama serve)")
        print(f"  2. Model is installed (ollama pull {OLLAMA_MODEL})")
        sys.exit(1)

    # Check: Did AI want to use tools?
    if not response.get("message", {}).get("tool_calls"):
        print("🤖 AI answered directly (no tools needed):")
        print(response["message"]["content"])
        return

    # Process tool calls
    messages = [
        {"role": "user", "content": user_msg},
        response["message"],
    ]

    for tool_call in response["message"]["tool_calls"]:
        tool_name = tool_call["function"]["name"]
        args = tool_call["function"]["arguments"]

        # Parse if arguments are JSON string
        if isinstance(args, str):
            args = json.loads(args)

        print(f"🔧 Tool requested: {tool_name}")
        print(f"📝 Arguments: {args}")

        # Execute the tool
        tool_result = await execute_tool(tool_name, args)
        print(f"✅ Tool result: {tool_result}\n")

        # Keep the tool identity and arguments alongside its response.
        result = (
            tool_result.structured_content
            if hasattr(tool_result, "structured_content")
            else {"result": str(tool_result)}
        )
        messages.append(
            {
                "role": "tool",
                "content": json.dumps(
                    {"tool": tool_name, "arguments": args, "result": result},
                    ensure_ascii=False,
                ),
            },
        )

    print(messages)

    # Send tool results back to AI for final answer
    final = chat_with_model(
        [
            *messages,
            {
                "role": "user",
                "content": (
                    "Now produce the final answer using all tool results. "
                    "Include both the greeting and the addition result."
                ),
            },
        ],
        temperature=0,
    )

    print("🤖 Final AI response:")
    print(final["message"]["content"])


if __name__ == "__main__":
    asyncio.run(main())
