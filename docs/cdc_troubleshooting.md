# Custom Data Commons (CDC) Troubleshooting Guide

This document covers common issues encountered when setting up and loading data into a Custom Data Commons instance.

---

## Issue 1: CSV Files Not Being Imported (0 CSV files found)

### Symptoms
- Data container logs show: `Found 0 csv files to import`
- Only MCF files are processed
- `observations` table in SQLite database is empty
- `report.json` only shows MCF file imports

### Diagnosis
Check the data container logs:
```bash
docker logs <container_name> 2>&1 | grep "csv files"
```

Verify observations table:
```bash
sqlite3 /path/to/datacommons/datacommons.db "SELECT COUNT(*) FROM observations;"
```

### Cause 1: Invalid fields in config.json

The `config.json` file contained fields that are not recognized by the data importer:

**Incorrect config.json:**
```json
{
  "inputFiles": {
    "data.csv": {
      "importType": "observations",    // NOT VALID
      "entityType": "Country",         // NOT VALID
      "provenance": "My Source",
      "format": "variablePerRow",
      "columnMappings": { ... }
    }
  }
}
```

**Correct config.json:**
```json
{
  "inputFiles": {
    "data.csv": {
      "provenance": "My Source",
      "format": "variablePerRow",
      "columnMappings": {
        "entity": "observationAbout",
        "date": "observationDate",
        "value": "value",
        "variable": "variableMeasured",
        "unit": "unit",
        "measurementMethod": "measurementMethod"
      }
    }
  },
  "sources": {
    "Source Name": {
      "url": "https://example.com",
      "provenances": {
        "My Source": "https://example.com/data"
      }
    }
  }
}
```

**Valid fields for inputFiles entries:**
- `provenance` (required) - must match a provenance in `sources`
- `format` (optional) - `variablePerRow` or default (variablePerColumn)
- `columnMappings` (optional) - maps default column names to your custom names

### Cause 2: Glob patterns with subdirectories not supported

**Does NOT work:**
```json
{
  "inputFiles": {
    "subfolder/*.csv": { ... },
    "data/exports/*.csv": { ... }
  }
}
```

**Works:**
```json
{
  "inputFiles": {
    "mydata.csv": { ... },
    "exports.csv": { ... }
  }
}
```

### Fix
1. Move CSV files to the same directory as `config.json`
2. Use explicit filenames without glob patterns or subdirectory paths

```bash
# Move files to root of INPUT_DIR
cp subfolder/*.csv /path/to/input_dir/
```

---

## Issue 2: Container Cannot Find Database After Clearing Data

### Symptoms
```
Cannot open sqlite database
error accessing sqlite db file: /path/to/datacommons.db (no such file or directory)
```

### Cause
The services container (`datacommons-services`) expects the database to already exist. If you delete the `datacommons/` folder, you must re-run the data container first.

### Fix
Always run containers in this order:
1. **Data container** (creates/updates database):
   ```bash
   docker run --env-file custom_dc/env.list \
     -v /path/to/custom_dc:/path/to/custom_dc \
     gcr.io/datcom-ci/datacommons-data:stable
   ```

2. **Services container** (serves the data):
   ```bash
   docker run -d --name custom-dc \
     --env-file custom_dc/env.list \
     -p 8080:8080 \
     -v /path/to/custom_dc:/path/to/custom_dc \
     gcr.io/datcom-ci/datacommons-services:stable
   ```

---

## Issue 3: Variables Not Showing in Statistical Variable Explorer

### Symptoms
- Data loads successfully (observations in database)
- Variables don't appear in the Statistical Variable Explorer UI
- NL search doesn't find your variables

### Diagnosis
1. Check if observations exist:
   ```bash
   sqlite3 datacommons.db "SELECT COUNT(*) FROM observations;"
   ```

2. Check if variable triples exist:
   ```bash
   sqlite3 datacommons.db "SELECT COUNT(*) FROM triples WHERE predicate='typeOf' AND object_id='StatisticalVariable';"
   ```

### Cause
Statistical variables need TWO things to appear in the sidebar:
1. **StatisticalVariable definitions** in MCF files (typeOf, name, etc.)
2. **memberOf predicates** connecting them to a StatVarGroup hierarchy

### Fix
**Step 1:** Create a StatVarGroup hierarchy MCF file (`statvar_hierarchy.mcf`):

```mcf
# Root group - connects to an existing category like Economy
Node: dcid:dc/g/MyData
typeOf: dcs:StatVarGroup
name: "My Custom Data"
specializationOf: dcid:dc/g/Economy

# Sub-groups
Node: dcid:dc/g/MyData_Category1
typeOf: dcs:StatVarGroup
name: "Category 1"
specializationOf: dcid:dc/g/MyData

Node: dcid:dc/g/MyData_Category2
typeOf: dcs:StatVarGroup
name: "Category 2"
specializationOf: dcid:dc/g/MyData
```

**Step 2:** Add `memberOf` predicates to your variables (`statvar_memberof.mcf`):

```mcf
Node: dcid:MyVariable1
memberOf: dcid:dc/g/MyData_Category1

Node: dcid:MyVariable2
memberOf: dcid:dc/g/MyData_Category2
```

**Step 3:** For many variables, generate memberOf statements programmatically:

```python
# gen_memberof.py
variables = [...]  # Get from database or CSV

mcf_lines = []
for var in variables:
    if 'Category1' in var:
        group = 'dc/g/MyData_Category1'
    else:
        group = 'dc/g/MyData_Category2'

    mcf_lines.append(f"Node: dcid:{var}")
    mcf_lines.append(f"memberOf: dcid:{group}")
    mcf_lines.append("")

with open('statvar_memberof.mcf', 'w') as f:
    f.write('\n'.join(mcf_lines))
```

Place all MCF files in the same directory as config.json and re-run the data container.

---

## Issue 4: Column Mapping Not Working

### Symptoms
- CSV file is found but data not imported correctly
- Errors about missing columns

### Cause
The `columnMappings` format maps FROM default names TO your custom names.

### Fix
**Default column names for variablePerRow format:**
- `entity` → your entity column
- `variable` → your variable column
- `date` → your date column
- `value` → your value column
- `unit` → your unit column (optional)
- `measurementMethod` → your measurement method column (optional)

**Example:**
If your CSV has columns: `observationAbout, observationDate, value, variableMeasured`

```json
"columnMappings": {
  "entity": "observationAbout",
  "date": "observationDate",
  "value": "value",
  "variable": "variableMeasured"
}
```

---

## Issue 5: `dcid:` Prefix in Variable Names

### Symptoms
Your CSV has values like `dcid:MyVariable` in the variable column.

### Resolution
The data importer automatically strips the `dcid:` prefix. This is handled correctly - no action needed.

**CSV input:**
```csv
variableMeasured
dcid:Exports_EconomicActivity_AnimalsLive
```

**Stored in database as:**
```
Exports_EconomicActivity_AnimalsLive
```

---

## Useful Debugging Commands

### Check database contents
```bash
# Count observations
sqlite3 datacommons.db "SELECT COUNT(*) FROM observations;"

# Sample observations
sqlite3 datacommons.db "SELECT * FROM observations LIMIT 5;"

# List unique variables
sqlite3 datacommons.db "SELECT DISTINCT variable FROM observations LIMIT 20;"

# List unique entities
sqlite3 datacommons.db "SELECT DISTINCT entity FROM observations LIMIT 20;"

# Count triples
sqlite3 datacommons.db "SELECT COUNT(*) FROM triples;"
```

### Check import report
```bash
cat /path/to/datacommons/process/report.json
```

### Check container logs
```bash
# Data container (run without -d to see output)
docker run --env-file env.list -v ... gcr.io/datcom-ci/datacommons-data:stable

# Services container
docker logs custom-dc 2>&1 | tail -100
```

### Test APIs
```bash
# Check if data is accessible
curl "http://localhost:8080/api/observations/series?entities=country/IND&variables=YOUR_VARIABLE"

# Search for variables
curl "http://localhost:8080/api/nl/search-indicators?queries=exports&limit_per_index=10"
```

---

## Issue 6: Data Loaded But Variables Don't Have `hasData: true`

### Symptoms
- Variables appear in hierarchy but show as grayed out
- API returns variables but `hasData` is `false`

### Cause
The variable DCIDs in your MCF file don't match the variable names in your CSV.

### Fix
Ensure the variable names in your CSV `variableMeasured` column match exactly with the `dcid` in your MCF file (without the `dcid:` prefix in CSV).

**MCF file:**
```mcf
Node: dcid:Exports_EconomicActivity_AnimalsLive
typeOf: dcid:StatisticalVariable
name: "Exports of Live Animals"
```

**CSV file:**
```csv
variableMeasured
dcid:Exports_EconomicActivity_AnimalsLive
```

Or without prefix:
```csv
variableMeasured
Exports_EconomicActivity_AnimalsLive
```

---

## Quick Reference: Two-Container Workflow

Always follow this order when loading/reloading data:

```bash
# Step 1: Run DATA container (processes CSV/MCF, creates database)
docker run --env-file custom_dc/env.list \
  -v /path/to/custom_dc:/path/to/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

# Step 2: Run SERVICES container (serves the website)
docker run -d --name custom-dc \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v /path/to/custom_dc:/path/to/custom_dc \
  -v /path/to/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

**To reload data:**
```bash
# 1. Stop and remove services container
docker rm -f custom-dc

# 2. Clear existing data
rm -rf /path/to/custom_dc/eidb/datacommons

# 3. Re-run data container
docker run --env-file custom_dc/env.list \
  -v /path/to/custom_dc:/path/to/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

# 4. Re-run services container
docker run -d --name custom-dc ...
```

---

## Quick Reference: Available Parent StatVarGroups

When creating your hierarchy, you can attach to these existing groups:

| Group DCID | Display Name |
|------------|--------------|
| `dc/g/Root` | Root (top level) |
| `dc/g/Agriculture` | Agriculture |
| `dc/g/Demographics` | Demographics |
| `dc/g/Economy` | Economy |
| `dc/g/Education` | Education |
| `dc/g/Energy` | Energy |
| `dc/g/Environment` | Environment |
| `dc/g/Health` | Health |
| `dc/g/Housing` | Housing |
| `dc/g/Crime` | Crime |

Example:
```mcf
Node: dcid:dc/g/MyExportData
typeOf: dcs:StatVarGroup
name: "My Export Data"
specializationOf: dcid:dc/g/Economy
```

---

## Quick Reference: API URLs for Testing

### Observations API
```bash
# Get time series data
curl "http://localhost:8080/api/observations/series?entities=country/IND&variables=YOUR_VARIABLE"

# Get single point data
curl "http://localhost:8080/api/observations/point?entities=country/IND&variables=YOUR_VARIABLE&date=2021"
```

### Variable Info API
```bash
# Get variable metadata
curl "http://localhost:8080/api/variable/info?dcids=YOUR_VARIABLE"

# Get variable group info
curl -X POST "http://localhost:8080/api/variable-group/info" \
  -H "Content-Type: application/json" \
  -d '{"dcid": "dc/g/YOUR_GROUP"}'
```

### Search API
```bash
# Search for variables by keyword
curl "http://localhost:8080/api/nl/search-indicators?queries=exports&limit_per_index=20"
```

### Source Info API
```bash
# List all data sources
curl "http://localhost:8080/api/node/propvals/in?prop=typeOf&dcids=Source"
```

---

## Quick Reference: Correct File Structure

```
custom_dc/
├── eidb/                              # INPUT_DIR / OUTPUT_DIR
│   ├── config.json                    # Configuration file
│   ├── mydata.csv                     # CSV files (in root, not subdirectories)
│   ├── moredata.csv
│   ├── schema.mcf                     # StatisticalVariable definitions
│   ├── statvar_hierarchy.mcf          # StatVarGroup hierarchy
│   ├── statvar_memberof.mcf           # memberOf predicates for variables
│   └── datacommons/                   # Generated by data container
│       ├── datacommons.db             # SQLite database
│       ├── nl/                        # NL embeddings
│       │   ├── sentences.csv
│       │   └── embeddings/
│       │       └── embeddings.csv
│       └── process/
│           └── report.json            # Import report
└── env.list                           # Environment variables
```

---

## Quick Reference: Complete config.json Example

```json
{
  "inputFiles": {
    "exports_data.csv": {
      "provenance": "Export Statistics",
      "format": "variablePerRow",
      "columnMappings": {
        "entity": "observationAbout",
        "date": "observationDate",
        "value": "value",
        "variable": "variableMeasured",
        "unit": "unit",
        "measurementMethod": "measurementMethod"
      }
    },
    "imports_data.csv": {
      "provenance": "Import Statistics"
    }
  },
  "sources": {
    "Ministry of Commerce": {
      "url": "https://commerce.gov.in/",
      "provenances": {
        "Export Statistics": "https://commerce.gov.in/exports",
        "Import Statistics": "https://commerce.gov.in/imports"
      }
    }
  }
}
```
