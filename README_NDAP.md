# NDAP Demo — Custom Data Commons

**National Data & Analytics Platform** · AI Data Agent demo built on Google Data Commons + Gemini

Built by **CloudSufi** for **NITI Aayog, Government of India** · Go-live: 15 June 2026

---

## Architecture

```
Browser (:8080)
    └── Docker: DC Services container (nginx → gunicorn :7070)
            └── Docker: DC Data container → SQLite DB
    └── MCP Server (Python, :3000) — DC knowledge graph tools
    └── AI Proxy (Flask, :5001) — LLM orchestration + SSE streaming
```

Four components must be running simultaneously:

| Component | Port | How to start |
|-----------|------|-------------|
| DC Services (Docker) | 8080 | Already running as `awesome_jang` |
| AI Proxy | 5001 | `python additional_features/mcp_proxy_only.py` |
| MCP Server | 3000 | `datacommons-mcp serve http --port 3000` |
| *(DC Data container — run once to build SQLite)* | — | See Step 1 |

---

## Prerequisites

- Docker Desktop running
- Python 3.10+
- API keys: Gemini, OpenRouter (Gemma 3 27B), Google Maps

---

## Setup & Run

### Step 1 — Build the SQLite database (first time or after CSV changes)

```bash
cd website/

docker run --rm \
  --env-file custom_dc/env.list \
  -v /Users/yashtripathi/ndap-eidb:/Users/yashtripathi/ndap-eidb \
  gcr.io/datcom-ci/datacommons-data:stable
```

> `INPUT_DIR` and `OUTPUT_DIR` in `env.list` must point to the folder containing the CSVs.
> Symlink: `ln -s $(pwd)/custom_dc/eidb /Users/yashtripathi/ndap-eidb`

### Step 2 — Start DC Services container

```bash
docker run -d \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -v /Users/yashtripathi/ndap-eidb:/Users/yashtripathi/ndap-eidb \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v $(pwd)/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-website-compose:stable
```

The website is now live at **http://localhost:8080**

### Step 3 — Configure AI Proxy

Copy the example config and fill in your API keys:

```bash
cp additional_features/config.json.example additional_features/config.json
# Edit config.json — add Gemini API key, OpenRouter API key, filestore IDs
```

Key fields in `config.json`:

```json
{
  "gemini": {
    "api_keys": ["YOUR_GEMINI_API_KEY"],
    "filestores": ["fileSearchStores/YOUR_FILESTORE_ID"],
    "mcp_model": "gemini-3-flash-preview"
  },
  "openrouter": {
    "api_key": "YOUR_OPENROUTER_API_KEY",
    "synthesis_model": "google/gemma-3-27b-it",
    "api_base": "https://openrouter.ai/api/v1"
  },
  "knowledge_base": { "enabled": true },
  "query_param_key": "AISummit2026"
}
```

### Step 4 — Start the AI Proxy

```bash
cd website/
source proxy-env/bin/activate      # or: python3 -m venv proxy-env && pip install -r additional_features/requirements.txt
cd additional_features
python mcp_proxy_only.py
```

Proxy starts on **http://localhost:5001**
Health check: `curl http://localhost:5001/health?key=AISummit2026`

### Step 5 — Start the MCP Server

```bash
cd website/
source customdc-env/bin/activate
python -m uv tool run --from datacommons-mcp==1.1.4 datacommons-mcp serve http \
  --port 3000 --host 0.0.0.0 --skip-api-key-validation
```

MCP starts on **http://localhost:3000**

---

## Usage

Open **http://localhost:8080** in a browser.

- The landing page shows the NDAP portal (matching ndap.niti.gov.in style)
- Click **AI Data Agent** or any sector/dataset card to open the chat
- Type a question in plain language, e.g.:
  - *"Show milk production across Indian states in 2023"*
  - *"What is India's GDP trend from 2015 to 2023?"*
  - *"Compare unemployment in Maharashtra, Bihar and Kerala"*
  - *"Show CPI inflation across Indian states in 2023"*

### Model selection (Settings panel)

The Settings panel (gear icon) has a **Backend Model** selector:
- **Auto (default)** — uses model priority from config.json (OpenRouter → Gemini)
- **Gemini 3 Flash** — fastest, Google cloud
- **OpenRouter — Gemma 3 27B** — open model via OpenRouter
- **Sarvam AI** — multilingual Indian language support

You can also force a model via URL: `?model=openrouter`

### Dry Run Report

The pre-demo test report is available at:
`http://localhost:8080/custom_dc/custom/dryrun_report.html`

---

## Data

All datasets live in `custom_dc/eidb/`. Each dataset needs:
- A `.csv` file (format: `variablePerRow`)
- A `.tmcf` schema file
- A `.mcf` StatVar definition file
- An entry in `custom_dc/eidb/config.json`

### Included datasets (748K+ observations)

| Dataset | Entity level | Years |
|---------|-------------|-------|
| GDP Annual (India) | National | 2012–2024 |
| GSDP Current / Constant | State | 2012–2023 |
| GVA (4 estimate types) | National | 2012–2024 |
| CPI (Consumer Price Index) | State + National | 2012–2024 |
| Merchandise Exports / Imports | Commodity × Country | 2014–2024 |
| MSME commodity trade | Commodity | 2014–2024 |
| MSME country trade | Country | 2014–2024 |
| Worker Population Ratio | State | 2011–2023 |
| ASI (Factory statistics) | State | 2011–2021 |
| NII (Non-financial instruments) | National | 2012–2023 |
| Population (NITI) | State | 2001–2036 |
| Population urban | State | 2001–2036 |
| Milk Production (state-wise) | State | 2001–2023 |
| Milk Production (national) | National | 1991–2024 |
| Milk PCA (per capita availability) | National | 1991–2024 |
| TB Notifications | National | 2018–2023 |
| PLFS Unemployment (state-wise) | State | 2024 |
| Census 2011 PCA (state-wise) | State | 2011 |
| Dengue (state-wise) | State | 2015–2024 |

### Adding new datasets

1. Place CSV + MCF + TMCF files in `custom_dc/eidb/`
2. Add entry to `custom_dc/eidb/config.json`
3. Re-run Step 1 (data container) to rebuild SQLite
4. Restart DC Services container

---

## Key Files

| File | Purpose |
|------|---------|
| `additional_features/mcp_proxy_only.py` | AI orchestration — MCP tool calls, KB queries, LLM synthesis, SSE streaming |
| `additional_features/config.json` | API keys, model names, prompts (not committed — use config.json.example) |
| `additional_features/config.json.example` | Sanitized config template |
| `server/templates/custom_dc/custom/homepage.html` | Chat UI, landing page, client-side JS |
| `server/templates/custom_dc/custom/base.html` | NDAP nav/header/footer branding |
| `static/custom_dc/custom/overrides.css` | NDAP color palette overrides |
| `static/custom_dc/custom/logo.png` | NDAP logo |
| `static/custom_dc/custom/dryrun_report.html` | Pre-demo dry run report |
| `custom_dc/eidb/config.json` | DC ingestion config (one entry per dataset) |
| `custom_dc/eidb/statvar_hierarchy.mcf` | Left sidebar topic tree |
| `custom_dc/env.list` | Docker env vars (DC_API_KEY, MAPS_API_KEY, INPUT/OUTPUT_DIR) |

---

## RAG / Knowledge Base

The AI proxy uses Gemini File Search (Grounding) for policy document queries.

- `knowledge_base.enabled: true` in config.json activates KB queries
- Filestores are Gemini File API stores (uploaded separately via `create_knowledge_base.py`)
- Current filestore: MSME policies + NDAP economic datasets
- PDF corpus is in `additional_features/RAG_Corpus/` (not committed, ~500MB)

To rebuild the KB:
```bash
cd additional_features/
python create_knowledge_base.py   # uploads PDFs to Gemini File API
# Copy the returned filestore ID into config.json → gemini.filestores
```

---

## Known Issues / Demo Notes

- **Ladakh on map**: DC shows J&K and Ladakh as separate UTs (post-2019 bifurcation). Datasets that predate bifurcation show Ladakh as empty/gray. Fix: add separate Ladakh rows to affected CSVs.
- **SVG negative viewBox**: Chart legend renders incorrectly when a dataset has sparse state coverage. Cosmetic only.
- **Response time**: ~35–45s per query (OpenRouter Gemma 3 27B). Population/census queries ~60s.
- **Map queries**: Confirmed working for milk production, unemployment, GSDP, CPI, population.

---

## Team

| Name | Role |
|------|------|
| Yash Tripathi (CloudSufi) | Lead dev — setup, data, AI, UI |
| Ishan Jaggi (CloudSufi) | Data preparation |
| Saurabh Gupta (CloudSufi) | Lead |
| Vasudev Nayak | Demo coordination |

---

*Built on [Google Data Commons](https://datacommons.org) · Powered by Gemini AI*
