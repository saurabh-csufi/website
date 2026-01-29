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

import copy
import json
import logging
import random
import re
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package, "-q"])


try:
    from flask import Flask, jsonify, request, Response, stream_with_context
    from flask_cors import CORS
except ImportError:
    print("Installing flask, flask-cors...")
    install_package("flask")
    install_package("flask-cors")
    from flask import Flask, jsonify, request, Response, stream_with_context
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

# Backend config cache
_config_cache = None
_config_mtime = 0


def load_config() -> dict:
    """Load configuration from config.json file."""
    global _config_cache, _config_mtime

    config_path = Path(__file__).parent / 'config.json'

    if not config_path.exists():
        logger.warning(f"Config file not found at {config_path}")
        return {}

    # Check if file was modified
    current_mtime = config_path.stat().st_mtime
    if _config_cache is not None and current_mtime == _config_mtime:
        return _config_cache

    try:
        with open(config_path, 'r') as f:
            _config_cache = json.load(f)
            _config_mtime = current_mtime
            logger.info("Config loaded/reloaded from config.json")
            return _config_cache
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def get_current_datetime_ist() -> str:
    """Get current date/time in Indian Standard Time format."""
    # IST is UTC+5:30
    from datetime import timezone, timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    return now.strftime("%A, %B %d, %Y at %I:%M %p IST")


def inject_datetime(prompt: str) -> str:
    """Replace {{CURRENT_DATETIME}} placeholder with current IST datetime."""
    return prompt.replace('{{CURRENT_DATETIME}}', get_current_datetime_ist())


def get_api_keys() -> list:
    """Load API keys from config (list or single key for backward compat)."""
    config = load_config()
    gemini_config = config.get("gemini", {})
    keys = gemini_config.get("api_keys", [])
    if not keys:
        # Fallback to single api_key for backward compatibility
        single_key = gemini_config.get("api_key", "")
        if single_key and not single_key.startswith("DEPRECATED"):
            keys = [single_key]
    return keys


def get_query_param_key() -> str:
    """Get the secret key for query param overrides from config."""
    config = load_config()
    return config.get("query_param_key", "AISummit2026")  # Default fallback


def apply_query_overrides(config: dict, query_params: dict) -> dict:
    """Apply query parameter overrides to config.

    Returns a new config dict with overrides applied (does not modify original).
    """
    if not query_params:
        return config

    # Deep copy to avoid modifying cached config
    effective = copy.deepcopy(config)

    # Model override
    if query_params.get("model"):
        effective["gemini"]["mcp_model"] = query_params["model"]
        effective["gemini"]["kb_model"] = query_params["model"]

    # Knowledge base toggle
    if query_params.get("kb_enabled"):
        enabled = query_params["kb_enabled"].lower() == "true"
        effective["knowledge_base"]["enabled"] = enabled

    # MCP thinking budget override
    if query_params.get("mcp_thinking"):
        effective["thinking"]["mcp_level"] = query_params["mcp_thinking"]

    # Synthesis thinking budget override
    if query_params.get("synthesis_thinking"):
        effective["thinking"]["synthesis_level"] = query_params["synthesis_thinking"]

    return effective


# ============================================================
# SESSION LOGGER - Comprehensive logging for debugging & audit
# ============================================================

class SessionLogger:
    """Comprehensive session-based logging for debugging and audit."""

    def __init__(self, session_id: str = None):
        """Initialize or resume a session logger.

        Args:
            session_id: Optional existing session ID for follow-up messages.
                        If None, generates a new session ID.
        """
        self.session_id = session_id or self._generate_session_id()
        self.logs_dir = Path(__file__).parent / 'logs'
        self.logs_dir.mkdir(exist_ok=True)
        self.log_file = self.logs_dir / f"{self.session_id}.log"
        self.entries = []
        self._write_header()

    def _generate_session_id(self) -> str:
        """Generate a short readable session ID.

        Format: YYMMDD-HHMMSS-XXXX (e.g., 260128-143052-a7f3)
        """
        timestamp = datetime.now().strftime("%y%m%d-%H%M%S")
        short_uuid = uuid.uuid4().hex[:4]
        return f"{timestamp}-{short_uuid}"

    def _write_header(self):
        """Write session header to log file (only if new file)."""
        if self.log_file.exists():
            # Resuming existing session - add continuation marker
            with open(self.log_file, 'a') as f:
                f.write(f"\n{'='*80}\n")
                f.write(f"CONTINUATION @ {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n")
        else:
            # New session - write header
            with open(self.log_file, 'w') as f:
                f.write(f"{'='*80}\n")
                f.write(f"SESSION LOG: {self.session_id}\n")
                f.write(f"Started: {datetime.now().isoformat()}\n")
                f.write(f"{'='*80}\n\n")

    def log(self, event_type: str, data: dict):
        """Log an event with full request/response details."""
        timestamp = datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "event_type": event_type,
            "data": data
        }
        self.entries.append(entry)

        # Write to file immediately
        with open(self.log_file, 'a') as f:
            f.write(f"\n--- {event_type} @ {timestamp} ---\n")
            f.write(json.dumps(data, indent=2, default=str))
            f.write("\n")

    def log_user_message(self, message: str, history_count: int = 0):
        """Log the user's input message."""
        self.log("USER_MESSAGE", {
            "message": message,
            "history_messages": history_count
        })

    def log_gemini_request(self, model: str, endpoint: str, payload_info: dict):
        """Log outgoing Gemini API request."""
        self.log("GEMINI_REQUEST", {
            "model": model,
            "endpoint": endpoint,
            "payload": payload_info
        })

    def log_gemini_response(self, model: str, response: dict, duration_ms: float):
        """Log incoming Gemini API response."""
        self.log("GEMINI_RESPONSE", {
            "model": model,
            "duration_ms": round(duration_ms, 2),
            "response": self._truncate_response(response)
        })

    def log_mcp_tool_call(self, tool_name: str, arguments: dict):
        """Log MCP tool call request."""
        self.log("MCP_TOOL_REQUEST", {
            "tool_name": tool_name,
            "arguments": arguments
        })

    def log_mcp_tool_result(self, tool_name: str, result: Any, duration_ms: float, status: str = "success"):
        """Log MCP tool call result."""
        result_str = json.dumps(result, default=str) if isinstance(result, dict) else str(result)
        self.log("MCP_TOOL_RESPONSE", {
            "tool_name": tool_name,
            "duration_ms": round(duration_ms, 2),
            "status": status,
            "result": result_str[:2000] + "..." if len(result_str) > 2000 else result_str
        })

    def log_kb_query(self, message: str, result: str, duration_ms: float):
        """Log Knowledge Base query."""
        self.log("KB_QUERY", {
            "query": message,
            "duration_ms": round(duration_ms, 2),
            "result_length": len(result),
            "result_preview": result[:500] + "..." if len(result) > 500 else result
        })

    def log_synthesis_start(self, context_parts: list):
        """Log synthesis phase start."""
        self.log("SYNTHESIS_START", {
            "context_sources": context_parts
        })

    def log_final_response(self, text: str, chart_config: dict = None, total_duration_ms: float = None):
        """Log the final response sent to user."""
        self.log("FINAL_RESPONSE", {
            "text_length": len(text),
            "text_preview": text[:500] + "..." if len(text) > 500 else text,
            "chart_config": chart_config,
            "total_duration_ms": round(total_duration_ms, 2) if total_duration_ms else None
        })

    def log_error(self, error_type: str, error_message: str, context: dict = None):
        """Log an error."""
        self.log("ERROR", {
            "error_type": error_type,
            "error_message": str(error_message),
            "context": context or {}
        })

    def _truncate_response(self, response: dict) -> dict:
        """Truncate large responses for logging."""
        response_str = json.dumps(response, default=str)
        if len(response_str) > 5000:
            return {"_truncated": True, "length": len(response_str), "preview": response_str[:5000]}
        return response


# Flask app
app = Flask(__name__)
CORS(app)

# Global state
session_id = None
tools_cache = None


def mcp_request(method: str, params: dict = None, is_notification: bool = False) -> dict:
    """Send a JSON-RPC request or notification to the MCP server.

    Args:
        method: The JSON-RPC method name
        params: Optional parameters
        is_notification: If True, sends as notification (no id, no response expected)
    """
    global session_id  # Needed to SET the global session_id from response headers

    payload = {
        "jsonrpc": "2.0",
        "method": method
    }

    # Notifications don't have an id
    if not is_notification:
        payload["id"] = int(time.time() * 1000)

    if params:
        payload["params"] = params

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"
    }

    if session_id:
        headers["Mcp-Session-Id"] = session_id

    try:
        # For notifications, we send but don't expect a response
        if is_notification:
            requests.post(
                MCP_URL,
                json=payload,
                headers=headers,
                timeout=5
            )
            return {"result": "notification sent"}

        response = requests.post(
            MCP_URL,
            json=payload,
            headers=headers,
            timeout=120,
            stream=True
        )

        # Log response details for debugging
        logger.info(f"MCP Response - Status: {response.status_code}, Headers: {dict(response.headers)}")

        # Get session ID from response (try multiple header variations)
        session_header = (
            response.headers.get("Mcp-Session-Id") or
            response.headers.get("mcp-session-id") or
            response.headers.get("MCP-Session-ID")
        )
        if session_header:
            session_id = session_header
            logger.info(f"Got MCP session ID from headers: {session_id}")
        else:
            logger.warning(f"No session ID in response headers. Available headers: {list(response.headers.keys())}")

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

    # Send initialized notification (no id, no response expected)
    mcp_request("notifications/initialized", {}, is_notification=True)
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


def fix_tool_arguments(name: str, arguments: dict) -> dict:
    """Fix common parameter mistakes made by LLMs."""
    args = arguments.copy()

    if name == "get_observations":
        # Fix 1: If date_range_start/end provided but date != 'range', fix it
        has_range_params = args.get("date_range_start") or args.get("date_range_end")
        if has_range_params and args.get("date") != "range":
            logger.info("Fixing: Setting date='range' because date_range params provided")
            args["date"] = "range"

        # Fix 2: Ensure date has a default if not provided
        if "date" not in args:
            args["date"] = "latest"

        # Fix 3: Remove null/None values that might cause issues
        args = {k: v for k, v in args.items() if v is not None}

    if name == "search_indicators":
        # Fix: Ensure places is a list
        if "places" in args and isinstance(args["places"], str):
            args["places"] = [args["places"]]

    return args


def call_tool(name: str, arguments: dict, session_logger: Optional[SessionLogger] = None) -> Any:
    """Call a tool on the MCP server with optional logging."""
    # Fix common parameter mistakes
    fixed_args = fix_tool_arguments(name, arguments)
    if fixed_args != arguments:
        logger.info(f"Fixed arguments: {arguments} -> {fixed_args}")

    # Log tool call request
    if session_logger:
        session_logger.log_mcp_tool_call(name, fixed_args)

    start_time = time.time()

    result = mcp_request("tools/call", {
        "name": name,
        "arguments": fixed_args
    })

    duration_ms = (time.time() - start_time) * 1000

    if "result" in result:
        # Log successful result
        if session_logger:
            session_logger.log_mcp_tool_result(name, result["result"], duration_ms, "success")
        return result["result"]

    # Log error result
    error_result = {"error": result.get("error", "Unknown error")}
    if session_logger:
        session_logger.log_mcp_tool_result(name, error_result, duration_ms, "error")
    return error_result


def check_data_availability(tool_calls_list: list) -> dict:
    """Check if MCP tool calls returned useful data.

    Returns:
        dict with keys:
        - has_data: bool
        - no_variables_found: bool (search_indicators returned empty)
        - no_observations_found: bool (get_observations returned empty)
        - message: str (user-friendly message if no data)
    """
    no_variables = False
    has_any_observations = False  # Track if ANY observation has data
    all_observations_empty = True  # Track if ALL observations are empty
    search_called = False
    observations_called = False

    for tc in tool_calls_list:
        result_str = tc.get('result', '')
        result_str_lower = result_str.lower()
        tool_name = tc.get('name', '')

        if tool_name == 'search_indicators':
            search_called = True
            # Check if no variables found
            if 'no indicators found' in result_str_lower or \
               '"variables": []' in result_str_lower or \
               'no matching' in result_str_lower or \
               'could not find' in result_str_lower or \
               ('"indicators":' in result_str_lower and '[]' in result_str_lower):
                no_variables = True

        elif tool_name == 'get_observations':
            observations_called = True

            # Check if THIS observation has actual data (time_series with values)
            # Look for patterns like: "time_series": [["2024", 14984.0]] (has data)
            # vs: "time_series": [] (empty)

            # Check for non-empty time_series with actual values
            has_data_pattern = re.search(r'"time_series":\s*\[\s*\[', result_str)
            if has_data_pattern:
                has_any_observations = True
                all_observations_empty = False

            # Also check for valid source_id (not "unknown")
            valid_source = re.search(r'"source_id":\s*"(?!unknown)[^"]+', result_str_lower)
            if valid_source and has_data_pattern:
                has_any_observations = True
                all_observations_empty = False

            # Check if this specific observation is empty
            is_empty = ('no data' in result_str_lower or
                       '"observations": []' in result_str_lower or
                       '"time_series": []' in result_str_lower or
                       '"time_series":[]' in result_str_lower or
                       'no observations' in result_str_lower)

            if not is_empty:
                all_observations_empty = False

    # Determine if we have usable data
    # We have data if: we found variables AND at least one observation has data
    if search_called and no_variables:
        has_data = False
    elif observations_called and all_observations_empty and not has_any_observations:
        has_data = False
    else:
        has_data = has_any_observations or (observations_called and not all_observations_empty)

    # Build user-friendly message
    message = None
    if not has_data:
        if no_variables:
            message = "We didn't find any matching data variables for your query."
        elif observations_called and all_observations_empty:
            message = "We found the data variable but there are no observations available."
        else:
            message = "We didn't find data for your query."

    return {
        'has_data': has_data,
        'no_variables_found': no_variables,
        'no_observations_found': all_observations_empty,
        'search_called': search_called,
        'observations_called': observations_called,
        'message': message
    }


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
        <li><a href="/api/config">/api/config</a> - Get backend config (no API key)</li>
        <li>POST /api/chat/stream - Full chat with streaming</li>
    </ul>
    <h3>Prerequisite</h3>
    <p>Make sure the MCP server is running:</p>
    <code>python3 -m uv tool run datacommons-mcp serve http --port {MCP_PORT}</code>
    </body>
    </html>
    """


# ============================================================
# NEW BACKEND API ENDPOINTS FOR GEMINI CALLS
# ============================================================

@app.route("/api/config", methods=["GET"])
def get_config_endpoint():
    """Return sanitized config (without API key) for frontend."""
    config = load_config()
    if not config:
        return jsonify({"success": False, "error": "Config not loaded"}), 500

    # Return config without sensitive data
    safe_config = {
        "gemini": {
            "api_base": config.get("gemini", {}).get("api_base", ""),
            "mcp_model": config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview"),
            "kb_model": config.get("gemini", {}).get("kb_model", "gemini-3-flash-preview"),
        },
        "mcp": config.get("mcp", {}),
        "knowledge_base": config.get("knowledge_base", {}),
        "thinking": config.get("thinking", {}),
        "has_api_key": bool(config.get("gemini", {}).get("api_key")),
    }
    return jsonify({"success": True, "config": safe_config})


def build_thinking_config(thinking_value: str) -> dict:
    """Build thinking configuration for Gemini 3 models."""
    level_map = {
        "minimal": 128,
        "low": 1024,
        "medium": 8192,
        "high": 24576
    }

    if thinking_value in level_map:
        budget = level_map[thinking_value]
    else:
        try:
            budget = int(thinking_value)
            budget = max(0, min(24576, budget))
        except ValueError:
            budget = 1024  # default to low

    return {
        "thinkingConfig": {
            "thinkingBudget": budget
        }
    }


def gemini_request(
    messages: list,
    system_instruction: str,
    model: str,
    tools: list = None,
    temperature: float = 0.3,
    thinking_level: str = None,
    response_schema: dict = None,
    stream: bool = False,
    session_logger: Optional[SessionLogger] = None
) -> Generator | dict:
    """Make a request to the Gemini API with key rotation and retry.

    Args:
        messages: Conversation history in Gemini format
        system_instruction: System prompt
        model: Model name (e.g., 'gemini-3-flash-preview')
        tools: Optional list of function declarations
        temperature: Sampling temperature
        thinking_level: Optional thinking budget level
        response_schema: Optional JSON schema for structured output
        stream: If True, returns a generator for SSE streaming
        session_logger: Optional SessionLogger for comprehensive logging

    Returns:
        If stream=False: dict with response
        If stream=True: Generator yielding text chunks
    """
    config = load_config()
    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Get all available keys
    all_keys = get_api_keys()
    if not all_keys:
        return {"error": "No Gemini API keys configured in config.json"}

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    # Build the payload (same for all attempts)
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": temperature,
        }
    }

    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": inject_datetime(system_instruction)}]
        }

    if tools:
        payload["tools"] = [{"functionDeclarations": tools}]

    if thinking_level:
        payload["generationConfig"].update(build_thinking_config(thinking_level))

    if response_schema:
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = response_schema

    endpoint = "streamGenerateContent" if stream else "generateContent"

    # Log request (once, before attempting)
    if session_logger:
        session_logger.log_gemini_request(model, endpoint, {
            "messages_count": len(messages),
            "has_tools": bool(tools),
            "tool_count": len(tools) if tools else 0,
            "temperature": temperature,
            "thinking_level": thinking_level,
            "has_response_schema": bool(response_schema),
            "stream": stream,
            "total_keys_available": len(all_keys)
        })

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        attempt_count += 1

        # Build URL with current key
        url = f"{api_base}/{model}:{endpoint}"
        if stream:
            url += f"?key={api_key}&alt=sse"
        else:
            url += f"?key={api_key}"

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("GEMINI_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        start_time = time.time()

        try:
            if stream:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    stream=True,
                    timeout=120
                )
                # Check for rate limit before streaming
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    logger.warning(f"API key rate limited, switching to next key...")
                    continue  # Immediately try next key
                if response.status_code in [500, 503]:
                    last_error = f"Server error ({response.status_code})"
                    logger.warning(f"Server error {response.status_code}, switching to next key...")
                    continue  # Try next key
                return _stream_gemini_response(response, session_logger)
            else:
                response = requests.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=120
                )

                # Check for rate limit - immediately switch key
                if response.status_code == 429:
                    last_error = "Rate limited (429)"
                    logger.warning(f"API key rate limited, switching to next key...")
                    continue  # Immediately try next key

                # Check for other retryable errors (500, 503)
                if response.status_code in [500, 503]:
                    last_error = f"Server error ({response.status_code})"
                    logger.warning(f"Server error {response.status_code}, switching to next key...")
                    continue  # Try next key

                result = response.json()

                # Log response
                if session_logger:
                    duration_ms = (time.time() - start_time) * 1000
                    session_logger.log_gemini_response(model, result, duration_ms)

                return result

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"Request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"Gemini API error: {e}")
            if session_logger:
                session_logger.log_error("GEMINI_API_ERROR", str(e), {"attempt": attempt_count, "model": model})
            continue

    # All keys exhausted
    error_msg = f"All {len(all_keys)} API keys failed. Last error: {last_error}"
    logger.error(error_msg)
    if session_logger:
        session_logger.log_error("GEMINI_ALL_KEYS_EXHAUSTED", error_msg, {"total_keys": len(all_keys)})
    return {"error": error_msg}


def _stream_gemini_response(response, session_logger: Optional[SessionLogger] = None) -> Generator:
    """Parse streaming response from Gemini API."""
    start_time = time.time()
    total_text = ""

    for line in response.iter_lines():
        if line:
            line_str = line.decode('utf-8')
            if line_str.startswith('data: '):
                try:
                    data = json.loads(line_str[6:])
                    if 'candidates' in data and data['candidates']:
                        candidate = data['candidates'][0]
                        if 'content' in candidate and 'parts' in candidate['content']:
                            for part in candidate['content']['parts']:
                                if 'text' in part:
                                    total_text += part['text']
                                    yield part['text']
                except json.JSONDecodeError:
                    continue

    # Log streaming completion
    if session_logger:
        duration_ms = (time.time() - start_time) * 1000
        session_logger.log("GEMINI_STREAM_COMPLETE", {
            "duration_ms": round(duration_ms, 2),
            "total_text_length": len(total_text)
        })


def execute_mcp_tool_loop(
    user_message: str,
    history: list,
    max_iterations: int = 5,
    session_logger: Optional[SessionLogger] = None,
    effective_config: dict = None
) -> tuple:
    """Execute the MCP tool calling loop.

    Args:
        user_message: The user's query
        history: Conversation history
        max_iterations: Maximum tool calling iterations
        session_logger: Optional SessionLogger for comprehensive logging
        effective_config: Optional config dict with query param overrides applied

    Returns:
        tuple: (tool_results_text, tool_calls_list, final_response_text)
    """
    config = effective_config if effective_config else load_config()
    mcp_prompt = config.get("prompts", {}).get("mcp", "")
    mcp_model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
    thinking_level = config.get("thinking", {}).get("mcp_level", "low")

    # Get MCP tools
    tools = get_tools()
    if not tools:
        if session_logger:
            session_logger.log_error("MCP_TOOLS_UNAVAILABLE", "No MCP tools available")
        return "", [], "MCP tools not available"

    # Convert tools to Gemini format
    gemini_tools = [{
        "name": t.get("name", ""),
        "description": t.get("description", ""),
        "parameters": t.get("inputSchema", {"type": "object", "properties": {}})
    } for t in tools]

    # Build conversation - NO history for MCP calls (fresh search every time)
    # History is only used in synthesis phase for context
    contents = []
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    tool_calls_list = []
    all_tool_results = []

    for iteration in range(max_iterations):
        logger.info(f"MCP Tool Loop - Iteration {iteration + 1}/{max_iterations}")

        if session_logger:
            session_logger.log("MCP_LOOP_ITERATION", {"iteration": iteration + 1, "max": max_iterations})

        response = gemini_request(
            messages=contents,
            system_instruction=mcp_prompt,
            model=mcp_model,
            tools=gemini_tools,
            temperature=1.0,
            thinking_level=thinking_level,
            stream=False,
            session_logger=session_logger
        )

        if "error" in response:
            if session_logger:
                session_logger.log_error("MCP_LOOP_ERROR", response['error'])
            return "", tool_calls_list, f"Error: {response['error']}"

        # Check for function calls
        candidates = response.get("candidates", [])
        if not candidates:
            if session_logger:
                session_logger.log_error("MCP_NO_CANDIDATES", "No response from model")
            return "", tool_calls_list, "No response from model"

        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])

        function_calls = []
        text_response = ""

        for part in parts:
            if "functionCall" in part:
                function_calls.append(part["functionCall"])
            elif "text" in part:
                text_response += part["text"]

        # If no function calls, we're done
        if not function_calls:
            tool_results_text = "\n\n".join([
                f"Tool: {tc['name']}\nResult: {tc['result']}"
                for tc in tool_calls_list
            ])
            if session_logger:
                session_logger.log("MCP_LOOP_COMPLETE", {
                    "iterations_used": iteration + 1,
                    "tools_called": len(tool_calls_list),
                    "has_text_response": bool(text_response)
                })
            return tool_results_text, tool_calls_list, text_response

        # Execute function calls
        contents.append({"role": "model", "parts": parts})
        function_responses = []

        for fc in function_calls:
            tool_name = fc.get("name", "")
            tool_args = fc.get("args", {})

            logger.info(f"Executing MCP tool: {tool_name}")
            result = call_tool(tool_name, tool_args, session_logger=session_logger)

            # Convert result to string
            if isinstance(result, dict):
                if "content" in result and isinstance(result["content"], list):
                    result_text = "\n".join([
                        c.get("text", json.dumps(c)) for c in result["content"]
                    ])
                else:
                    result_text = json.dumps(result)
            else:
                result_text = str(result)

            tool_call_info = {
                "name": tool_name,
                "arguments": tool_args,
                "result": result_text[:500] + "..." if len(result_text) > 500 else result_text,
                "status": "error" if "error" in result_text.lower() else "success"
            }
            tool_calls_list.append(tool_call_info)
            all_tool_results.append(f"Tool: {tool_name}\nResult: {result_text}")

            function_responses.append({
                "functionResponse": {
                    "name": tool_name,
                    "response": {"result": result_text}
                }
            })

        contents.append({"role": "user", "parts": function_responses})

    # Max iterations reached
    tool_results_text = "\n\n".join(all_tool_results)
    if session_logger:
        session_logger.log("MCP_LOOP_MAX_ITERATIONS", {"tools_called": len(tool_calls_list)})
    return tool_results_text, tool_calls_list, "Max tool iterations reached"


def execute_kb_query(user_message: str, session_logger: Optional[SessionLogger] = None) -> dict:
    """Execute Knowledge Base query using file search with key rotation.

    Returns:
        dict with keys:
        - response: str (the response text)
        - sources: list of dicts with 'title' and 'uri'
    """
    config = load_config()
    kb_config = config.get("knowledge_base", {})

    if not kb_config.get("enabled", False):
        return {"response": "", "sources": []}

    kb_prompt = config.get("prompts", {}).get("kb", "")
    kb_model = config.get("gemini", {}).get("kb_model", "gemini-3-flash-preview")
    store_id = kb_config.get("store_id", "")

    if not store_id:
        return {"response": "", "sources": []}

    # Get all available keys
    all_keys = get_api_keys()
    if not all_keys:
        return {"response": "", "sources": []}

    api_base = config.get("gemini", {}).get("api_base", "https://generativelanguage.googleapis.com/v1beta/models")

    # Shuffle keys for random order
    keys_to_try = all_keys.copy()
    random.shuffle(keys_to_try)

    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": inject_datetime(kb_prompt)}]},
        "generationConfig": {"temperature": 0.3},
        "tools": [{
            "fileSearch": {
                "dynamicFileSearchConfig": {
                    "mode": "MODE_DYNAMIC",
                    "dynamicThreshold": 0.3
                }
            }
        }],
        "toolConfig": {
            "fileSearch": {
                "vectorStore": {"storeResourceId": store_id}
            }
        }
    }

    last_error = None
    attempt_count = 0

    for api_key in keys_to_try:
        attempt_count += 1
        start_time = time.time()

        # Log retry attempt (if not first attempt)
        if attempt_count > 1 and session_logger:
            session_logger.log("KB_KEY_ROTATION", {
                "attempt": attempt_count,
                "total_keys": len(all_keys),
                "reason": str(last_error)
            })

        try:
            url = f"{api_base}/{kb_model}:generateContent?key={api_key}"
            response = requests.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=60
            )

            # Check for rate limit - immediately switch key
            if response.status_code == 429:
                last_error = "Rate limited (429)"
                logger.warning(f"KB API key rate limited, switching to next key...")
                continue

            # Check for other retryable errors
            if response.status_code in [500, 503]:
                last_error = f"Server error ({response.status_code})"
                logger.warning(f"KB server error {response.status_code}, switching to next key...")
                continue

            data = response.json()

            candidates = data.get("candidates", [])
            result_text = ""
            sources = []

            if candidates:
                candidate = candidates[0]
                parts = candidate.get("content", {}).get("parts", [])
                result_text = "".join([p.get("text", "") for p in parts])

                # Extract grounding metadata for source citations
                grounding_metadata = candidate.get("groundingMetadata", {})
                grounding_chunks = grounding_metadata.get("groundingChunks", [])

                seen_titles = set()
                for chunk in grounding_chunks:
                    retrieved_context = chunk.get("retrievedContext", {})
                    if retrieved_context:
                        title = retrieved_context.get("title", "Unknown")
                        uri = retrieved_context.get("uri", "")
                        # Deduplicate by title
                        if title not in seen_titles:
                            seen_titles.add(title)
                            sources.append({
                                "title": title,
                                "uri": uri
                            })

            # Log KB query
            if session_logger:
                duration_ms = (time.time() - start_time) * 1000
                session_logger.log_kb_query(user_message, result_text, duration_ms)
                if sources:
                    session_logger.log("KB_SOURCES", {"sources": sources})

            return {"response": result_text, "sources": sources}

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            logger.warning(f"KB request timeout, trying next key...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"KB query error: {e}")
            if session_logger:
                session_logger.log_error("KB_QUERY_ERROR", str(e), {"query": user_message, "attempt": attempt_count})
            continue

    # All keys exhausted
    logger.error(f"KB query failed: All {len(all_keys)} API keys exhausted. Last error: {last_error}")
    if session_logger:
        session_logger.log_error("KB_ALL_KEYS_EXHAUSTED", f"All keys failed: {last_error}", {"total_keys": len(all_keys)})
    return {"response": "", "sources": []}


# Chart config schema for Gemini structured output (hardcoded - not user configurable)
CHART_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "should_render": {
            "type": "boolean",
            "description": "True if chart should be rendered (data exists)"
        },
        "viz_type": {
            "type": "string",
            "enum": ["line", "bar", "map", "ranking", "pie", "highlight", "gauge", "scatter", "slider"]
        },
        "title": {"type": "string"},
        "variable_dcids": {"type": "array", "items": {"type": "string"}},
        "place_dcids": {"type": "array", "items": {"type": "string"}},
        "parent_place": {"type": "string"},
        "child_place_type": {"type": "string"}
    },
    "required": ["should_render"]
}


def get_chart_config(mcp_results: str, user_message: str) -> dict:
    """Get chart configuration using structured output."""
    config = load_config()
    mcp_model = config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")

    prompt = f"""Based on the data query and results, determine if a chart should be rendered.

User Query: {user_message}

Data Results:
{mcp_results[:3000] if mcp_results else 'No data results'}

Extract variable DCIDs and place DCIDs from the results. Choose appropriate viz_type based on data type.
If no meaningful data for visualization, set should_render to false."""

    response = gemini_request(
        messages=[{"role": "user", "parts": [{"text": prompt}]}],
        system_instruction="You are a data visualization expert. Extract chart configuration from data results.",
        model=mcp_model,
        temperature=0.2,
        response_schema=CHART_CONFIG_SCHEMA,
        stream=False
    )

    try:
        if "candidates" in response:
            text = response["candidates"][0]["content"]["parts"][0].get("text", "{}")
            return json.loads(text)
    except Exception as e:
        logger.error(f"Chart config parse error: {e}")

    return {"should_render": False}


@app.route("/api/chat/stream", methods=["POST"])
def chat_stream():
    """Full chat workflow with SSE streaming.

    Phases:
    1. MCP Tools - Execute data queries (send tool call details)
    2. KB Query - Search knowledge base (if enabled)
    3. Synthesis - Stream final response with chart config

    Request body:
    {
        "message": "user query",
        "history": [...optional conversation history...],
        "session_id": "optional session ID for follow-up messages"
    }

    Query params (optional, requires valid key):
    - key: Secret key for config overrides (must match query_param_key in config)
    - model: Override mcp_model and kb_model
    - kb: "true" or "false" to toggle knowledge base
    - mcp_thinking: Override MCP thinking level
    - synthesis_thinking: Override synthesis thinking level

    Response: Server-Sent Events stream
    """
    global session_id  # MCP session ID

    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "Message required"}), 400

    user_message = data["message"]
    history = data.get("history", [])
    existing_session_id = data.get("session_id")  # From follow-up messages

    # Parse query parameters for config overrides
    query_params = {}
    secret_key = request.args.get("key", "")
    expected_key = get_query_param_key()

    if secret_key == expected_key:
        # Valid key - extract override params
        query_params = {
            "model": request.args.get("model"),  # e.g., "gemini-2.0-flash"
            "kb_enabled": request.args.get("kb"),  # "true" or "false"
            "mcp_thinking": request.args.get("mcp_thinking"),  # "low", "medium", "high", or budget number
            "synthesis_thinking": request.args.get("synthesis_thinking"),  # same options
        }
        # Remove None values
        query_params = {k: v for k, v in query_params.items() if v is not None}
        if query_params:
            logger.info(f"Query params override applied: {query_params}")
    elif secret_key:
        # Invalid key provided - log warning but continue with defaults
        logger.warning(f"Invalid query param key provided, ignoring overrides")

    # Create or resume session logger
    session_logger = SessionLogger(session_id=existing_session_id)

    def generate():
        nonlocal session_logger
        request_start_time = time.time()
        full_text = ""

        # Send session ID first so frontend can display it
        yield f"data: {json.dumps({'session_id': session_logger.session_id})}\n\n"

        # Log query params if present
        if query_params:
            session_logger.log("QUERY_PARAMS_OVERRIDE", query_params)

        # Log user message
        session_logger.log_user_message(user_message, len(history))

        config = load_config()
        if not config:
            session_logger.log_error("CONFIG_ERROR", "Backend config not loaded")
            yield f"data: {json.dumps({'error': 'Backend config not loaded'})}\n\n"
            return

        # Apply query param overrides to config
        effective_config = apply_query_overrides(config, query_params)

        # Ensure MCP is initialized (fix for tool calls not showing)
        mcp_ready = False
        if not session_id:
            logger.info("MCP session not initialized, attempting to connect...")
            session_logger.log("MCP_INIT_ATTEMPT", {"reason": "session_id was None"})
            if initialize_mcp():
                session_logger.log("MCP_INIT_SUCCESS", {"mcp_session_id": session_id})
                mcp_ready = True
            else:
                # Even if init returns False, try to get tools anyway
                # Some MCP servers work without session IDs
                session_logger.log("MCP_INIT_RETURNED_FALSE", {"trying_tools_anyway": True})
        else:
            mcp_ready = True

        # Double-check: if we have tools, MCP is working regardless of session_id
        tools = get_tools()
        if tools:
            mcp_ready = True
            session_logger.log("MCP_TOOLS_AVAILABLE", {"tool_count": len(tools), "tools": [t.get("name") for t in tools]})
        else:
            session_logger.log("MCP_NO_TOOLS", {"session_id": session_id})

        # Phase 1: MCP Tools
        mcp_enabled = effective_config.get("mcp", {}).get("enabled", True)
        mcp_results = ""
        tool_calls_list = []

        if mcp_enabled and mcp_ready:
            yield f"data: {json.dumps({'status': 'mcp_start', 'message': 'Querying data tools...'})}\n\n"

            mcp_results, tool_calls_list, mcp_text = execute_mcp_tool_loop(
                user_message, history, session_logger=session_logger,
                effective_config=effective_config
            )

            # Send each tool call for left sidebar
            for tc in tool_calls_list:
                yield f"data: {json.dumps({'type': 'tool_call', 'name': tc['name'], 'arguments': tc['arguments'], 'result': tc['result'], 'status': tc['status']})}\n\n"

            yield f"data: {json.dumps({'status': 'mcp_complete', 'tool_count': len(tool_calls_list)})}\n\n"

            # Check data availability and send status to frontend
            data_status = check_data_availability(tool_calls_list)
            yield f"data: {json.dumps({'data_status': data_status})}\n\n"

        elif mcp_enabled and not mcp_ready:
            session_logger.log("MCP_SKIPPED", {"reason": "MCP not connected or no tools available"})
            yield f"data: {json.dumps({'status': 'mcp_skipped', 'message': 'MCP server not connected'})}\n\n"

        # Phase 2: KB Query (if enabled)
        kb_response = ""
        kb_sources = []
        kb_enabled = effective_config.get("knowledge_base", {}).get("enabled", False)

        if kb_enabled:
            yield f"data: {json.dumps({'status': 'kb_start', 'message': 'Searching knowledge base...'})}\n\n"
            kb_result = execute_kb_query(user_message, session_logger=session_logger)
            kb_response = kb_result.get("response", "")
            kb_sources = kb_result.get("sources", [])
            # Send KB sources to frontend for inline citations
            if kb_sources:
                yield f"data: {json.dumps({'kb_sources': kb_sources})}\n\n"
            yield f"data: {json.dumps({'status': 'kb_complete'})}\n\n"

        # Phase 3: Synthesis with streaming
        yield f"data: {json.dumps({'status': 'synthesis_start', 'message': 'Generating response...'})}\n\n"

        synthesis_prompt = effective_config.get("prompts", {}).get("synthesis", "")
        synthesis_model = effective_config.get("gemini", {}).get("mcp_model", "gemini-3-flash-preview")
        thinking_level = effective_config.get("thinking", {}).get("synthesis_level", "low")

        # Build synthesis context with source labels for citations
        context_parts = []
        if mcp_results:
            context_parts.append(f"**DATA RESULTS [Source: Data Commons]:**\n{mcp_results}")
        if kb_response:
            # Include document names from kb_sources for proper citation
            kb_source_names = ", ".join([s['title'] for s in kb_sources]) if kb_sources else "Knowledge Base"
            context_parts.append(f"**POLICY INFORMATION [Sources: {kb_source_names}]:**\n{kb_response}")

        # Log synthesis start
        session_logger.log_synthesis_start(["MCP" if mcp_results else None, "KB" if kb_response else None])

        synthesis_message = f"""User Query: {user_message}

{chr(10).join(context_parts) if context_parts else 'No additional context available.'}

Please provide a comprehensive response combining all available information."""

        # Stream the synthesis response
        try:
            stream_gen = gemini_request(
                messages=[{"role": "user", "parts": [{"text": synthesis_message}]}],
                system_instruction=synthesis_prompt,
                model=synthesis_model,
                temperature=0.3,
                thinking_level=thinking_level,
                stream=True,
                session_logger=session_logger
            )

            if isinstance(stream_gen, dict) and "error" in stream_gen:
                session_logger.log_error("SYNTHESIS_ERROR", stream_gen['error'])
                yield f"data: {json.dumps({'error': stream_gen['error']})}\n\n"
                return

            for text_chunk in stream_gen:
                full_text += text_chunk
                yield f"data: {json.dumps({'text': text_chunk})}\n\n"

            # After streaming, programmatically append data request link if data was insufficient
            # This ensures the link always appears, regardless of whether the model included it
            if tool_calls_list:  # Only if we actually tried MCP tools
                data_avail = check_data_availability(tool_calls_list)
                if not data_avail.get('has_data', True):
                    # Check if link is already in the response
                    data_request_link = "https://docs.datacommons.org/contributing"
                    if data_request_link not in full_text:
                        link_text = "\n\n---\n\nIf you'd like to see this data in Data Commons, you can [submit a data request](https://docs.datacommons.org/contributing)."
                        full_text += link_text
                        yield f"data: {json.dumps({'text': link_text})}\n\n"

        except Exception as e:
            logger.error(f"Synthesis streaming error: {e}")
            session_logger.log_error("SYNTHESIS_STREAM_ERROR", str(e))
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # Get chart config (non-blocking)
        chart_config = get_chart_config(mcp_results, user_message)

        # Log final response
        total_duration_ms = (time.time() - request_start_time) * 1000
        session_logger.log_final_response(full_text, chart_config, total_duration_ms)

        # Send final event with timing info
        yield f"data: {json.dumps({'chart_config': chart_config, 'done': True, 'duration_ms': round(total_duration_ms, 0)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


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
