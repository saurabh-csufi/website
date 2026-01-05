# Custom Data Commons Deployment Guide

This guide documents how to deploy and run the Custom Data Commons website with the Gemini chat interface and MCP (Model Context Protocol) integration.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Browser (localhost:8080)                        │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Gemini Chat Interface                            │   │
│  │  - PDF upload & analysis                                             │   │
│  │  - MCP tool integration                                              │   │
│  │  - Multi-turn conversations                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
        │                           │                           │
        │ Gemini API               │ MCP Proxy                 │ Direct
        │ (function calling)       │ (REST + CORS)             │ Pages
        ▼                           ▼                           ▼
┌───────────────┐         ┌─────────────────┐         ┌─────────────────┐
│  Google AI    │         │   MCP Proxy     │         │  Custom DC      │
│  (Gemini)     │         │   (Port 5001)   │         │  Docker         │
│               │         │                 │         │  (Port 8080)    │
└───────────────┘         └────────┬────────┘         └─────────────────┘
                                   │
                                   │ JSON-RPC + SSE
                                   ▼
                          ┌─────────────────┐
                          │  MCP Server     │
                          │  (Port 3000)    │
                          │  datacommons-   │
                          │  mcp            │
                          └────────┬────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  Data Commons   │
                          │  API            │
                          │  (public or     │
                          │   custom DC)    │
                          └─────────────────┘
```

## Prerequisites

- **Python 3.11+**
- **Docker** installed and running
- **uv** package manager (`pip install uv`)
- **API Keys:**
  - Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
  - Data Commons API key from [apikeys.datacommons.org](https://apikeys.datacommons.org/) (for public DC)

## Quick Start

You need **3 terminals** to run the full stack.

> **IMPORTANT:** Services must be started in order. The MCP server validates its connection at startup, so Docker must be fully ready before starting MCP.

### Terminal 1: Custom DC Docker Container (Start First!)

```bash
cd /Users/saurabhgupta/Documents/2026/website

docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc:/Users/saurabhgupta/Documents/2026/website/custom_dc \
  -v /Users/saurabhgupta/Documents/2026/website/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

**Wait 30-60 seconds** until you see the server is ready (Flask/gunicorn listening).

**Verify Docker is ready before proceeding:**
```bash
curl http://localhost:8080/core/api/v2/node?nodes=country/USA
# Should return JSON data, not connection error
```

### Terminal 2: Data Commons MCP Server (Start After Docker is Ready!)

**Option A: Using Public Data Commons API**
```bash
export DC_API_KEY="your-data-commons-api-key"
python3 -m uv tool run datacommons-mcp serve http --port 3000
```

**Option B: Using Local Custom DC Instance** (see [Custom DC Configuration](#pointing-mcp-to-custom-data-commons) below)
```bash
export DC_TYPE="custom"
export CUSTOM_DC_URL="http://localhost:8080"
python3 -m uv tool run datacommons-mcp serve http --port 3000  --host 0.0.0.0 

--skip-api-key-validation
```

### Terminal 3: MCP Proxy Server

```bash
cd /Users/saurabhgupta/Documents/2026/website
python3 additional_features/mcp_proxy_only.py
```

### Access the Application

1. Open browser to **http://localhost:8080**
2. Enter your **Gemini API key** in the settings
3. Set **MCP Proxy URL** to `http://localhost:5001`
4. Enable **"Use MCP Tools"** toggle
5. Start chatting!

## Detailed Configuration

### Environment File (custom_dc/env.list)

Create or edit `custom_dc/env.list`:

```bash
# Required for Gemini chat
GEMINI_API_KEY=your-gemini-api-key

# Google Cloud (optional, for maps)
GOOGLE_CLOUD_PROJECT=your-project-id
MAPS_API_KEY=your-maps-api-key

# Debug mode
DEBUG=true
```

### Docker Run Options Explained

| Option | Description |
|--------|-------------|
| `--env-file custom_dc/env.list` | Load environment variables from file |
| `-p 8080:8080` | Expose port 8080 for web access |
| `-e DEBUG=true` | Enable debug mode |
| `-v .../custom_dc/sample/` | Mount sample data directory |
| `-v .../templates/custom_dc/custom` | Mount custom HTML templates |

### Port Configuration

| Service | Default Port | Environment Variable |
|---------|--------------|---------------------|
| Custom DC (Docker) | 8080 | N/A |
| MCP Server | 3000 | `MCP_PORT` |
| MCP Proxy | 5001 | `PROXY_PORT` |

To use different ports:
```bash
# MCP Server on port 3001
python3 -m uv tool run datacommons-mcp serve http --port 3001

# Proxy on port 5002
export MCP_PORT=3001
export PROXY_PORT=5002
python3 additional_features/mcp_proxy_only.py
```

## Pointing MCP to Custom Data Commons

By default, the MCP server queries the public Data Commons API. To query your local Custom DC instance instead:

### Required Environment Variables

```bash
export DC_API_KEY="your-api-key"      # Required (can be any value for local)
export DC_TYPE="custom"                # Tells MCP to use custom endpoint
export CUSTOM_DC_URL="http://localhost:8080"  # Your Custom DC URL
```

### Full Command

```bash
# Set environment variables
export DC_API_KEY="local-dev-key"
export DC_TYPE="custom"
export CUSTOM_DC_URL="http://localhost:8080"

# Start MCP server
python3 -m uv tool run datacommons-mcp serve http --port 3000
```

### Skip API Key Validation (Local Development)

If your local Custom DC doesn't require an API key:

```bash
export DC_TYPE="custom"
export CUSTOM_DC_URL="http://localhost:8080"
python3 -m uv tool run datacommons-mcp serve http --port 3000 --skip-api-key-validation
```

### Verification

After starting the MCP server with custom configuration, you should see it connect to your local instance. Test by asking questions about data that exists only in your Custom DC.

## Service Health Checks

### Check Custom DC Docker
```bash
curl http://localhost:8080
# Should return HTML page
```

### Check MCP Server
```bash
curl http://localhost:3000
# Should return JSON (may show SSE error in browser - that's expected)
```

### Check MCP Proxy
```bash
curl http://localhost:5001/health
# Should return: {"status": "ok", "mcp_url": "http://localhost:3000/mcp"}

curl http://localhost:5001/api/tools
# Should return list of available MCP tools
```

## Troubleshooting

### MCP Server Won't Start

**Error:** `uv: command not found`
```bash
pip install uv
```

**Error:** `DC_API_KEY not set`
```bash
export DC_API_KEY="your-key"
# Or for local dev:
python3 -m uv tool run datacommons-mcp serve http --port 3000 --skip-api-key-validation
```

**Error:** `InvalidDCInstanceError` or `Connection refused` when using Custom DC
```
requests.exceptions.ConnectionError: HTTPConnectionPool(host='localhost', port=8080):
Max retries exceeded... Connection refused
```

**Cause:** The Docker container is not running or not fully ready yet. The MCP server validates its connection at startup.

**Solution:**
1. Make sure Docker container is started FIRST
2. Wait 30-60 seconds for it to fully initialize
3. Verify with: `curl http://localhost:8080/core/api/v2/node?nodes=country/USA`
4. Only THEN start the MCP server with custom DC settings

### Proxy Can't Connect to MCP

**Error:** `Cannot connect to MCP server at http://localhost:3000/mcp`

1. Ensure MCP server is running in Terminal 2
2. Check the port matches (default 3000)
3. Verify with: `curl http://localhost:3000`

### Browser Shows CORS Errors

Make sure you're connecting to the **proxy** (port 5001), not the MCP server directly (port 3000). The proxy adds CORS headers.

### Docker Container Exits Immediately

Check Docker logs:
```bash
docker logs $(docker ps -lq)
```

Common issues:
- Port 8080 already in use: `lsof -i :8080` then kill the process
- Missing env file: ensure `custom_dc/env.list` exists

### Chat Not Using MCP Tools

1. Verify "Use MCP Tools" toggle is enabled
2. Check MCP Proxy URL is set to `http://localhost:5001`
3. Look for green "MCP Connected" indicator
4. Check browser console for errors

## Scripts for Convenience

### Start All Services (start_services.sh)

```bash
#!/bin/bash
# Save as start_services.sh

echo "Starting Custom DC services..."

# Terminal 1: Docker (run in background)
echo "Starting Docker container..."
docker run -d \
  --name custom-dc \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v $(pwd)/custom_dc/:$(pwd)/custom_dc/ \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable

echo "Waiting for Docker to start..."
sleep 10

# Terminal 2: MCP Server (background)
echo "Starting MCP server..."
export DC_API_KEY="${DC_API_KEY:-local-dev}"
python3 -m uv tool run datacommons-mcp serve http --port 3000 &
MCP_PID=$!

sleep 5

# Terminal 3: Proxy (foreground)
echo "Starting MCP proxy..."
python3 additional_features/mcp_proxy_only.py

# Cleanup on exit
trap "kill $MCP_PID; docker stop custom-dc; docker rm custom-dc" EXIT
```

### Stop All Services

```bash
# Stop Docker
docker stop custom-dc && docker rm custom-dc

# Kill processes on ports
lsof -ti:3000 | xargs kill -9 2>/dev/null
lsof -ti:5001 | xargs kill -9 2>/dev/null
```

## File Locations

| File | Purpose |
|------|---------|
| `custom_dc/env.list` | Environment variables for Docker |
| `custom_dc/sample/` | Sample data CSV files |
| `server/templates/custom_dc/custom/homepage.html` | Chat interface UI |
| `additional_features/mcp_proxy_only.py` | MCP proxy server |
| `docs/gemini_chat_setup.md` | Gemini chat documentation |
| `docs/datacommons_mcp_integration.md` | MCP integration details |

## Related Documentation

- [Gemini Chat Setup](gemini_chat_setup.md) - Chat interface configuration
- [Data Commons MCP Integration](datacommons_mcp_integration.md) - MCP technical details
- [Data Commons MCP Docs](https://docs.datacommons.org/mcp/) - Official MCP documentation
- [Custom DC Quickstart](https://docs.datacommons.org/custom_dc/quickstart.html) - Official Custom DC guide
