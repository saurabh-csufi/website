# Data Commons MCP Integration Guide

This guide explains how to integrate the Data Commons MCP (Model Context Protocol) server with the AI chat interface.

## Overview

The Data Commons MCP server provides tools for querying statistical data from Data Commons. This integration allows the AI assistant to fetch real-time data about demographics, economics, health, environment, and more.

### Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│    Browser      │ ───► │  MCP Proxy       │ ───► │  MCP Server     │
│   (Frontend)    │      │  (Flask + CORS)  │      │ (datacommons-   │
│                 │      │  Port 5001       │      │  mcp)           │
│                 │      │                  │      │  Port 3000      │
└─────────────────┘      └──────────────────┘      └─────────────────┘
         │                                                  │
         │                                                  │
         ▼                                                  ▼
┌─────────────────┐                              ┌─────────────────┐
│   Gemini API    │                              │ Data Commons    │
│ (function       │                              │     API         │
│  calling)       │                              │                 │
└─────────────────┘                              └─────────────────┘
```

**Why a proxy?**
- The MCP server uses the MCP protocol which requires session management
- Browsers need CORS headers for cross-origin requests
- The proxy handles protocol translation and adds CORS support

## Prerequisites

1. **Python 3.9+** installed
2. **Data Commons API Key** from https://apikeys.datacommons.org/
3. **Gemini API Key** from https://aistudio.google.com/apikey

## Quick Start

### Step 1: Set Environment Variables

```bash
# Required: Data Commons API key
export DC_API_KEY=your-data-commons-api-key

# Optional: Customize ports (defaults shown)
export MCP_PORT=3000
export PROXY_PORT=5001
```

### Step 2: Start the MCP Proxy Server

```bash
cd /path/to/website
python additional_features/mcp_proxy_server.py
```

You should see output like:
```
2024-XX-XX XX:XX:XX - INFO - Starting MCP server on port 3000...
2024-XX-XX XX:XX:XX - INFO - MCP server is ready!
2024-XX-XX XX:XX:XX - INFO - Initializing MCP session...
2024-XX-XX XX:XX:XX - INFO - MCP session initialized
2024-XX-XX XX:XX:XX - INFO - Available tools: ['get_statistical_data', 'search_entities', ...]
2024-XX-XX XX:XX:XX - INFO - Starting proxy server on port 5001...
```

### Step 3: Start the Docker Container (in another terminal)

```bash
docker run -it \
  -p 8080:8080 \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v $(pwd)/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

### Step 4: Access the Chat Interface

1. Open http://localhost:8080
2. Enter your Gemini API key
3. Enable "Use MCP Tools" toggle
4. Start asking questions about data!

## API Reference

### Proxy Server Endpoints

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "mcp_port": 3000
}
```

#### GET /api/tools
List available MCP tools in Gemini-compatible format.

**Response:**
```json
{
  "success": true,
  "tools": [
    {
      "name": "get_statistical_data",
      "description": "Get statistical observations for a place",
      "parameters": {
        "type": "object",
        "properties": {
          "place": { "type": "string", "description": "Place DCID or name" },
          "stat_var": { "type": "string", "description": "Statistical variable" }
        },
        "required": ["place", "stat_var"]
      }
    }
  ],
  "raw_tools": [...]
}
```

#### POST /api/call
Execute a tool call.

**Request:**
```json
{
  "name": "get_statistical_data",
  "arguments": {
    "place": "country/USA",
    "stat_var": "Count_Person"
  }
}
```

**Response:**
```json
{
  "success": true,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Population of United States: 331,449,281 (2020)"
      }
    ]
  }
}
```

## Available MCP Tools

The Data Commons MCP server provides these tools:

| Tool | Description |
|------|-------------|
| `get_statistical_data` | Get statistical observations for places |
| `search_entities` | Search for entities (places, topics) |
| `get_entity_info` | Get detailed information about an entity |
| `compare_places` | Compare statistics across multiple places |
| `get_time_series` | Get historical data over time |

## Frontend Integration

### JavaScript Example

```javascript
const MCP_PROXY_URL = 'http://localhost:5001';

// Get available tools
async function getTools() {
  const response = await fetch(`${MCP_PROXY_URL}/api/tools`);
  const data = await response.json();
  return data.tools;
}

// Call a tool
async function callTool(name, arguments) {
  const response = await fetch(`${MCP_PROXY_URL}/api/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, arguments })
  });
  const data = await response.json();
  return data.result;
}

// Integration with Gemini function calling
async function chat(userMessage) {
  // 1. Get tool definitions
  const tools = await getTools();

  // 2. Send to Gemini with tools
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=${GEMINI_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ role: 'user', parts: [{ text: userMessage }] }],
        tools: [{ functionDeclarations: tools }]
      })
    }
  );

  const data = await response.json();

  // 3. Check for function calls
  const functionCalls = data.candidates?.[0]?.content?.parts?.filter(p => p.functionCall);

  if (functionCalls?.length > 0) {
    // 4. Execute tool calls via MCP proxy
    const results = [];
    for (const part of functionCalls) {
      const fc = part.functionCall;
      const result = await callTool(fc.name, fc.args);
      results.push({
        functionResponse: {
          name: fc.name,
          response: result
        }
      });
    }

    // 5. Send results back to Gemini
    // ... continue conversation
  }
}
```

## Troubleshooting

### "DC_API_KEY not set" Error

```bash
export DC_API_KEY=your-api-key-here
```

Get your key from: https://apikeys.datacommons.org/

### MCP Server Won't Start

1. Check if port 3000 is in use:
   ```bash
   lsof -i :3000
   ```

2. Kill any existing process:
   ```bash
   kill -9 $(lsof -t -i:3000)
   ```

3. Check uv is installed:
   ```bash
   pip install uv
   ```

### CORS Errors in Browser

Make sure you're connecting to the proxy server (port 5001), not the MCP server (port 3000) directly.

### Tool Calls Return Empty Results

1. Verify DC_API_KEY is valid
2. Check the MCP server logs for errors
3. Try simpler queries first (e.g., "population of USA")

### "Connection Refused" Errors

1. Check both servers are running:
   ```bash
   curl http://localhost:3000  # MCP server
   curl http://localhost:5001/health  # Proxy server
   ```

2. Ensure no firewall is blocking the ports

## Advanced Configuration

### Custom Port Configuration

```bash
export MCP_PORT=3001      # MCP server port
export PROXY_PORT=5002    # Proxy server port
python additional_features/mcp_proxy_server.py
```

### Running in Background

```bash
nohup python additional_features/mcp_proxy_server.py > mcp_proxy.log 2>&1 &
```

### Docker Network (if needed)

If running the proxy in Docker alongside other containers:

```bash
docker network create dc-network

# Run MCP proxy
docker run -d --name mcp-proxy \
  --network dc-network \
  -e DC_API_KEY=$DC_API_KEY \
  -p 5001:5001 \
  python:3.11 \
  python /app/mcp_proxy_server.py

# Run Data Commons
docker run -it \
  --network dc-network \
  -p 8080:8080 \
  gcr.io/datcom-ci/datacommons-services:stable
```

## Reference Links

- [Data Commons MCP Package](https://pypi.org/project/datacommons-mcp/)
- [Data Commons API Documentation](https://docs.datacommons.org/api/)
- [Google ADK Documentation](https://google.github.io/adk-docs/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [Gemini Function Calling](https://ai.google.dev/gemini-api/docs/function-calling)
