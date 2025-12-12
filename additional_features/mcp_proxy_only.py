#!/usr/bin/env python3
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
MCP Proxy Server (Proxy-Only Mode)

This script provides a REST API with CORS for browser-based frontends
to communicate with an already running Data Commons MCP server.

Prerequisites:
    Start the MCP server first:
    python3 -m uv tool run datacommons-mcp serve http --port 3000

Usage:
    python mcp_proxy_only.py
"""

import json
import logging
import os
import subprocess
import sys
import time
from typing import Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])


try:
    from flask import Flask, jsonify, request
    from flask_cors import CORS
except ImportError:
    print("Installing flask, flask-cors...")
    install_package("flask")
    install_package("flask-cors")
    from flask import Flask, jsonify, request
    from flask_cors import CORS

try:
    import requests
except ImportError:
    print("Installing requests...")
    install_package("requests")
    import requests


# Configuration
MCP_PORT = int(os.environ.get("MCP_PORT", 3000))
PROXY_PORT = int(os.environ.get("PROXY_PORT", 5001))
MCP_URL = f"http://localhost:{MCP_PORT}/mcp"

# Flask app
app = Flask(__name__)
CORS(app)

# Global state
session_id = None
tools_cache = None


def mcp_request(method: str, params: dict = None) -> dict:
    """Send a JSON-RPC request to the MCP server."""
    global session_id

    request_id = int(time.time() * 1000)

    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "id": request_id
    }
    if params:
        payload["params"] = params

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    if session_id:
        headers["Mcp-Session-Id"] = session_id

    try:
        response = requests.post(
            MCP_URL,
            json=payload,
            headers=headers,
            timeout=120,
            stream=True
        )

        # Get session ID from response
        if "Mcp-Session-Id" in response.headers:
            session_id = response.headers["Mcp-Session-Id"]

        content_type = response.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # Parse SSE response
            result = None
            for line in response.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: "):
                        try:
                            data = json.loads(line_str[6:])
                            if "result" in data:
                                result = data["result"]
                            elif "error" in data:
                                return {"error": data["error"]}
                        except json.JSONDecodeError:
                            continue
            return {"result": result} if result else {"error": "No result"}
        else:
            return response.json()

    except requests.exceptions.ConnectionError:
        return {"error": f"Cannot connect to MCP server at {MCP_URL}. Make sure it's running!"}
    except Exception as e:
        return {"error": str(e)}


def initialize_mcp() -> bool:
    """Initialize the MCP session."""
    global session_id

    logger.info("Initializing MCP session...")

    result = mcp_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {"roots": {"listChanged": True}},
        "clientInfo": {"name": "dc-mcp-proxy", "version": "1.0.0"}
    })

    if "error" in result:
        logger.error(f"Failed to initialize MCP: {result['error']}")
        return False

    logger.info(f"MCP session initialized: {session_id}")

    # Send initialized notification
    mcp_request("notifications/initialized", {})
    return True


def get_tools() -> list:
    """Get available tools from MCP server."""
    global tools_cache

    if tools_cache:
        return tools_cache

    result = mcp_request("tools/list", {})

    if "result" in result and result["result"] and "tools" in result["result"]:
        tools_cache = result["result"]["tools"]
        return tools_cache

    return []


def call_tool(name: str, arguments: dict) -> Any:
    """Call a tool on the MCP server."""
    result = mcp_request("tools/call", {
        "name": name,
        "arguments": arguments
    })

    if "result" in result:
        return result["result"]
    return {"error": result.get("error", "Unknown error")}


# Flask Routes

@app.route("/health", methods=["GET"])
def health():
    """Health check."""
    return jsonify({"status": "ok", "mcp_url": MCP_URL})


@app.route("/api/tools", methods=["GET"])
def list_tools():
    """List available tools."""
    global session_id

    if not session_id:
        if not initialize_mcp():
            return jsonify({"success": False, "error": "Cannot connect to MCP server. Make sure it's running on port 3000!"}), 503

    tools = get_tools()
    if not tools:
        return jsonify({"success": False, "error": "No tools available"}), 503

    # Convert to Gemini format
    gemini_tools = [{
        "name": t.get("name", ""),
        "description": t.get("description", ""),
        "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
    } for t in tools]

    return jsonify({"success": True, "tools": gemini_tools, "raw_tools": tools})


@app.route("/api/call", methods=["POST"])
def tool_call():
    """Execute a tool call."""
    global session_id

    if not session_id:
        if not initialize_mcp():
            return jsonify({"success": False, "error": "Cannot connect to MCP server"}), 503

    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"success": False, "error": "Tool name required"}), 400

    logger.info(f"Calling tool: {data['name']}")
    result = call_tool(data["name"], data.get("arguments", {}))
    return jsonify({"success": True, "result": result})


@app.route("/", methods=["GET"])
def index():
    return f"""
    <html>
    <head><title>MCP Proxy</title></head>
    <body>
    <h1>Data Commons MCP Proxy Server (Proxy-Only Mode)</h1>
    <p>MCP Server: {MCP_URL}</p>
    <p>Proxy Server: http://localhost:{PROXY_PORT}</p>
    <ul>
        <li><a href="/health">/health</a> - Health check</li>
        <li><a href="/api/tools">/api/tools</a> - List tools</li>
        <li>POST /api/call - Execute tool</li>
    </ul>
    <h3>Prerequisite</h3>
    <p>Make sure the MCP server is running:</p>
    <code>python3 -m uv tool run datacommons-mcp serve http --port {MCP_PORT}</code>
    </body>
    </html>
    """


def main():
    """Main entry point."""
    print("=" * 60)
    print("Data Commons MCP Proxy Server (Proxy-Only Mode)")
    print("=" * 60)
    print(f"\nExpecting MCP server at: http://localhost:{MCP_PORT}")
    print("\nMake sure you started the MCP server first:")
    print(f"  python3 -m uv tool run datacommons-mcp serve http --port {MCP_PORT}")

    # Try to connect to MCP server
    print("\nChecking MCP server connection...")
    if initialize_mcp():
        tools = get_tools()
        print(f"\nConnected! Found {len(tools)} tools:")
        for t in tools:
            print(f"  - {t.get('name')}")
    else:
        print("\nWARNING: Could not connect to MCP server")
        print("The proxy will start anyway - MCP server can be started later")

    # Start proxy
    print(f"\nStarting proxy on port {PROXY_PORT}...")
    print(f"Frontend should connect to: http://localhost:{PROXY_PORT}")
    print("\nPress Ctrl+C to stop")
    print("=" * 60)

    app.run(host="0.0.0.0", port=PROXY_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
