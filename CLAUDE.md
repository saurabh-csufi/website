# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **Data Commons Website** repository - a Custom Data Commons (CDC) deployment platform. It hosts the frontend for Data Commons, including custom DC instances, JavaScript client libraries, and web components.

Key directories for Custom DC work:
- `custom_dc/sample/` - Sample supplemental data and config.json
- `custom_dc/examples/` - More CSV data examples with config.json
- `server/templates/custom_dc/custom/` - Customizable HTML templates
- `static/custom_dc/custom/` - Customizable CSS and logo

## Development Commands

### Initial Setup
```bash
./run_test.sh --setup_all     # Setup all Python virtual environments
nvm use 18.4.0                # Set correct Node version
```

### Running Locally
```bash
./run_npm.sh                  # Watch and build static assets (run first, keep running)
./run_server.sh               # Start Flask server at localhost:8080
./run_server.sh -m            # Start with NL models enabled (requires NL server)
./run_server.sh -e lite       # Start without Maps API (place search disabled)
./run_server.sh -e custom     # Start with custom DC environment
./run_nl_server.sh -p 6060    # Start NL server (separate terminal)
./run_servers.sh              # Run both NL and website servers together
```

### Custom Data Commons Docker
```bash
./run_cdc_dev_docker.sh                              # Run with defaults (stable release)
./run_cdc_dev_docker.sh -e custom_dc/env.list        # Specify env file
./run_cdc_dev_docker.sh -a build_run -i myimage:tag  # Build and run custom image
./run_cdc_dev_docker.sh --help                       # Full documentation
```

### Testing
```bash
./run_test.sh -a              # Run all tests
./run_test.sh -p              # Run Python tests (server/tests/, shared/tests/, nl_server/tests/)
./run_test.sh -w              # Run webdriver tests
./run_test.sh --cdc           # Run Custom DC webdriver tests
./run_test.sh -c              # Run client-side (npm) tests
./run_test.sh -b              # Run npm build
./run_test.sh --explore       # Run explore integration tests
./run_test.sh --nl            # Run NL integration tests
./run_test.sh -g              # Update integration test golden files

# Webdriver recording modes
./run_test.sh -w --record     # Record new webdriver recordings
./run_test.sh -w --replay     # Replay from recordings (default)
./run_test.sh -w --live       # Run live without recordings
./run_test.sh -w --record --clean  # Delete existing recordings first
```

### Running Single Tests
```bash
# Python (pytest)
source server/.venv/bin/activate
python3 -m pytest server/tests/path/to/test.py -s
python3 -m pytest server/tests/path/to/test.py::TestClass::test_method -s

# JavaScript (Jest)
cd static && npm test -- path/to/test.tsx
cd static && npm test -- -u  # Update React snapshots
```

### Linting
```bash
./run_test.sh -f              # Fix all lint errors (Python + JS)
./run_test.sh -f py           # Fix Python lint only
./run_test.sh -f npm          # Fix JavaScript lint only
./run_test.sh -l              # Run client lint check (without fix)
```

## Architecture

### Server Components

1. **Website Server** (`server/`, `web_app.py`) - Flask app on port 8080
   - Routes in `server/routes/` organized by feature (browser, place, explore, nl, etc.)
   - Templates in `server/templates/` (Jinja2)
   - Config in `server/config/`

2. **NL Server** (`nl_server/`, `nl_app.py`) - Flask NL search server on port 6060
   - Spacy NLP models for entity recognition
   - Language model integration

3. **Mixer** (`mixer/` submodule) - Go gRPC backend API
   - Protocol buffers for communication
   - Runs on port 12345 (local), 8081 (with ESP proxy)

4. **Import Tools** (`import/` submodule) - Data loading and embeddings

### Frontend

- `static/` - Main website React/TypeScript code, Webpack bundled
- `packages/client` - JavaScript client library (@datacommonsorg/client)
- `packages/web-components` - Web components library
- `packages/react-tiles` - React tile components

### Virtual Environments

Each server has its own venv:
- `server/.venv` - Website server
- `nl_server/.venv` - NL server
- `.venv` - Combined (for tests)
- `tools/nl/embeddings/.venv` - Embeddings tools

### Environment Variables

Key variables for local development:
- `FLASK_ENV` - Server environment (local, custom, iitm, lite, webdriver, integration_test)
- `ENABLE_MODEL` - Enable NL language models
- `GOOGLE_CLOUD_PROJECT` - GCP project ID

## Git Workflow

```bash
git submodule update --init --recursive  # Initialize mixer/import submodules
./scripts/update_git_submodules.sh       # Update submodules to latest
```

## Dependencies

- Python 3.11-3.12 (3.13+ has torch compatibility issues)
- Node 18.4.0 (use `nvm use 18.4.0`)
- protoc 3.21.12
- ChromeDriver (must match Chrome version)
- uv package manager (`brew install uv`)
