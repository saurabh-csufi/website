# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Custom Data Commons (CDC)** deployment for the **NDAP demo** (National Data & Analytics Platform, NITI Aayog). The active working branch is `custom-dc-setup`. It extends Google's Data Commons with:
- Custom Indian government datasets loaded via Docker
- An AI chat interface powered by Gemini/Gemma/Sarvam models
- A Flask proxy server that orchestrates LLM + MCP tool calls
- NDAP-branded HTML/CSS templates

## Development Commands

### Initial Setup
```bash
./run_test.sh --setup_all     # Setup all Python virtual environments
nvm use 18.4.0                # Set correct Node version
```

### Running Locally (non-Docker)
```bash
./run_npm.sh                  # Watch and build static assets (run first, keep running)
./run_server.sh -e custom     # Start Flask server at localhost:8080 with custom DC env
./run_server.sh               # Start Flask server (default env)
./run_nl_server.sh -p 6060    # Start NL server in separate terminal
```

### Custom Data Commons Docker (primary workflow)
```bash
# Step 1 — Build SQLite from custom_dc/eidb/ CSVs
docker run -it --env-file custom_dc/env.list \
  -v /path/to/website/custom_dc:/path/to/website/custom_dc \
  gcr.io/datcom-ci/datacommons-data@sha256:5b701d36e04ad53d01bc532e8d9bf24f0f26ee7b5c69632965225c5639934e50

# Step 2 — Serve website + API on localhost:8080
docker run -it --env-file custom_dc/env.list -p 8080:8080 -e DEBUG=true \
  -v /path/to/data:/path/to/data \
  -v ./server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v ./static/custom_dc/custom:/workspace/server/dist/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services@sha256:60a43ea2eabf0cd4e957a715d97b0ab44047001c9f4e5f55b5cf37e4cb6e6ec3

# Or use the convenience wrapper:
./run_cdc_dev_docker.sh -e custom_dc/env.list
```

### AI Layer (run in separate terminals after Docker)
```bash
# MCP server on port 3000
python3 -m venv customdc-env && source customdc-env/bin/activate
pip install datacommons-mcp uv
export DC_TYPE="custom" CUSTOM_DC_URL="http://localhost:8080" DC_API_KEY=<key>
python -m uv tool run --from datacommons-mcp==1.1.4 datacommons-mcp serve http --port 3000 --host 0.0.0.0

# Proxy server on port 5001
python3 -m venv proxy-env && source proxy-env/bin/activate
pip install flask flask-cors requests
cd additional_features && cp config.json.example config.json  # then fill API keys
python mcp_proxy_only.py
```

### Testing
```bash
./run_test.sh -a              # Run all tests
./run_test.sh -p              # Python tests only
./run_test.sh --cdc           # Custom DC webdriver tests
./run_test.sh -c              # Client-side (npm) tests
./run_test.sh -b              # npm build check

# Single Python test
source server/.venv/bin/activate
python3 -m pytest server/tests/path/to/test.py::TestClass::test_method -s

# Single JS test
cd static && npm test -- path/to/test.tsx
```

### Linting
```bash
./run_test.sh -f              # Fix all lint errors (Python + JS)
./run_test.sh -f py           # Python only
./run_test.sh -f npm          # JS only
```

## Architecture

### Layer 1 — Data (Docker)

`custom_dc/eidb/` is the single source of truth for custom data. The Data Container reads it on startup and populates a SQLite DB.

Every file in `eidb/` must have a corresponding entry in `custom_dc/eidb/config.json`. The config uses `"format": "variablePerRow"` with `columnMappings` mapping CSV columns to DC observation fields (`observationAbout`, `observationDate`, `variableMeasured`, `value`, `unit`).

The left-sidebar topic hierarchy is controlled by `custom_dc/eidb/statvar_hierarchy.mcf`. Groups chain up via `specializationOf: dcid:dc/g/Root`. StatVar definitions live in `*_stat_vars.mcf` files; template mappings in `*.tmcf` files.

**After any change to `eidb/`:** re-run the Data Container (Step 1 above) before the Services Container.

### Layer 2 — Website Server (Docker / Flask)

The Services Container serves `server/` (Flask, Jinja2). For custom DC, only two directories are volume-mounted and hot-reloaded:
- `server/templates/custom_dc/custom/` — HTML overrides
- `static/custom_dc/custom/` — CSS (`overrides.css`) and assets (`logo.png`)

Template inheritance: `base.html` → page templates (`homepage.html`, `about.html`, etc.). The base template renders nav, header, footer; page templates override the `content` block. `OVERRIDE_CSS_PATH` in base.html injects `overrides.css` last.

### Layer 3 — AI / Chat (Flask Proxy)

`additional_features/mcp_proxy_only.py` is the AI orchestration layer. It:
1. Receives a user message at `POST /api/chat/stream`
2. Calls `GET /api/tools` on the DC MCP server (port 3000) to get available Data Commons tools
3. Sends user message + tools to the LLM (Gemini function-calling API)
4. Executes tool calls against the MCP server (`call_tool`)
5. Runs a second LLM pass (`execute_mcp_tool_loop`) to synthesize results
6. Streams the final response as SSE back to the browser

All configuration lives in `additional_features/config.json`:
- `gemini.api_keys` / `gemini.api_base` / `gemini.mcp_model` — LLM routing
- `prompts.mcp` — system prompt injected into every MCP reasoning call
- `prompts.synthesis` — system prompt for the final synthesis pass
- `mcp.server_url` — URL of the DC MCP server
- `thinking.mcp_level` / `thinking.synthesis_level` — thinking budget ("none"/"low"/"medium"/"high")

### Layer 4 — Chat Frontend (`homepage.html`)

`server/templates/custom_dc/custom/homepage.html` contains the entire chat UI as inline JS (~3000 lines). Key config block at the top:

```js
window.CHAT_CONFIG = {
  PROMPT_VERSION: '1.4.0',   // bump when prompts change (invalidates localStorage cache)
  models: { MCP_MODEL, KB_MODEL },
  api: { GEMINI_API_BASE },
  defaults: { mcpProxyUrl, kbStoreId, kbEnabled },
  systemInstructions: { mcp: `...`, kb: `...` }
}
```

The frontend calls `mcpProxyUrl + "/api/chat/stream"` and streams SSE. Model selection passes `model` as a body field. System prompts in `CHAT_CONFIG.systemInstructions.mcp` are sent client-side; `additional_features/config.json` prompts are applied server-side — **both must be kept in sync** when datasets change.

### Model Switching

All three supported models (Gemini, OpenRouter/Gemma, Sarvam) speak OpenAI-compatible chat completion. To add/swap a model:
1. Add keys and `api_base` to `additional_features/config.json`
2. In `mcp_proxy_only.py`, route to the correct base URL in `gemini_request()` based on an `active_model` config field or a request param
3. Expose the option in the frontend `CHAT_CONFIG.models` and the model-selector UI

## Key Files

| File | Purpose |
|------|---------|
| `custom_dc/env.list` | Docker env vars — DC_API_KEY, MAPS_API_KEY, INPUT_DIR, OUTPUT_DIR |
| `custom_dc/eidb/config.json` | DC data ingestion config — one entry per CSV |
| `custom_dc/eidb/statvar_hierarchy.mcf` | Left-sidebar topic tree |
| `additional_features/config.json` | API keys, model config, server-side prompts |
| `additional_features/mcp_proxy_only.py` | Flask proxy — all AI orchestration logic |
| `server/templates/custom_dc/custom/homepage.html` | Chat UI + client-side prompts + CHAT_CONFIG |
| `server/templates/custom_dc/custom/base.html` | Nav, header, footer (NDAP branding target) |
| `static/custom_dc/custom/overrides.css` | CSS overrides (NDAP palette) |
| `static/custom_dc/custom/logo.png` | Logo shown in nav |

## Data Format Reference

CSV files in `eidb/` use `variablePerRow` format:

```
entity,date,variable,value,unit,measurementMethod
country/IND,2023,MyStatVar_India,1234567,USDollar,MySource
```

StatVar MCF definition:
```
Node: dcid:MyStatVar_India
typeOf: dcs:StatisticalVariable
populationType: schema:Thing
measuredProperty: dcid:myMetric
name: "My Metric for India"
memberOf: dcid:dc/g/MyGroup
```

## Server Components

- **Website Server** (`server/`, `web_app.py`) — Flask, port 8080. Routes in `server/routes/`, Jinja2 templates in `server/templates/`
- **NL Server** (`nl_server/`, `nl_app.py`) — Flask NL search, port 6060
- **Mixer** (`mixer/` submodule) — Go gRPC API, port 12345
- **Import Tools** (`import/` submodule) — Data loading utilities

Virtual environments: `server/.venv`, `nl_server/.venv`, `.venv` (combined for tests)

## Dependencies

- Python 3.11–3.12 (3.13+ breaks torch)
- Node 18.4.0 (`nvm use 18.4.0`)
- protoc 3.21.12
- ChromeDriver (match installed Chrome version)
- `uv` (`brew install uv`)

## Git

```bash
git submodule update --init --recursive  # Initialize mixer/import submodules
./scripts/update_git_submodules.sh       # Update submodules
```
