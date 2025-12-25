# EIDB Data Setup Guide

This document describes all changes made to get the India Export Data (EIDB) working in the Custom Data Commons instance.

---

## Summary of Issues and Fixes

| Issue | Root Cause | Fix |
|-------|------------|-----|
| CSV files not imported | Invalid fields in config.json (`importType`, `entityType`) | Removed invalid fields |
| CSV files still not found | Glob patterns with subdirectories not supported | Moved CSVs to root directory |
| Variables not in sidebar | Missing StatVarGroup hierarchy and `memberOf` predicates | Created hierarchy MCF files |
| Variables under Economy | `specializationOf: dc/g/Economy` | Changed to `dc/g/Root` |

---

## 1. config.json Changes

### Original (Broken)
```json
{
  "inputFiles": {
    "eidb_commodity_wise_export/*.csv": {
      "importType": "observations",
      "entityType": "Country",
      "provenance": "Country Wise Export",
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
    "India Ministry of Commerce and Industry": {
      "url": "https://tradestat.commerce.gov.in/",
      "provenances": {
        "Country Wise Export": "https://tradestat.commerce.gov.in/eidb/country_wise_export"
      }
    }
  }
}
```

### Fixed Version
```json
{
  "inputFiles": {
    "msme_commodity_inr.csv": {
      "provenance": "Commodity Wise Export",
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
    "msme_country.csv": {
      "provenance": "Country Wise Export",
      "format": "variablePerRow",
      "columnMappings": {
        "entity": "observationAbout",
        "date": "observationDate",
        "variable": "variableMeasured",
        "value": "value",
        "unit": "unit",
        "measurementMethod": "measurementMethod"
      }
    }
  },
  "sources": {
    "India Ministry of Commerce and Industry": {
      "url": "https://tradestat.commerce.gov.in/",
      "provenances": {
        "Commodity Wise Export": "https://tradestat.commerce.gov.in/eidb/commodity_wise_export",
        "Country Wise Export": "https://tradestat.commerce.gov.in/eidb/country_wise_export"
      }
    }
  }
}
```

### Key Changes:
1. **Removed invalid fields:** `importType` and `entityType` are not valid
2. **Removed glob patterns:** `eidb_commodity_wise_export/*.csv` → `msme_commodity_inr.csv`
3. **Removed subdirectory paths:** Files must be in same directory as config.json
4. **Added all provenances:** Each provenance used in inputFiles must exist in sources

---

## 2. File Structure Changes

### Original Structure (Broken)
```
custom_dc/eidb/
├── config.json
├── consolidated_statvars.mcf
├── hscodes.mcf
├── msme_schema.mcf
├── eidb_commodity_wise_export/      # Subdirectory - NOT SUPPORTED
│   ├── msme_commodity_inr.csv
│   └── msme_commodity_usd.csv
└── eidb_country_wise_export/        # Subdirectory - NOT SUPPORTED
    ├── msme_country.csv
    └── msme_country_export.csv
```

### Fixed Structure
```
custom_dc/eidb/
├── config.json
├── consolidated_statvars.mcf        # StatisticalVariable definitions
├── hscodes.mcf                      # HS Code definitions
├── msme_schema.mcf                  # Schema definitions
├── statvar_hierarchy.mcf            # NEW: StatVarGroup hierarchy
├── statvar_memberof.mcf             # NEW: memberOf predicates
├── msme_commodity_inr.csv           # MOVED: CSV in root directory
├── msme_country.csv                 # MOVED: CSV in root directory
├── eidb_commodity_wise_export/      # Original location (kept for reference)
└── eidb_country_wise_export/        # Original location (kept for reference)
```

### Command to Move Files:
```bash
cp eidb_commodity_wise_export/msme_commodity_inr.csv .
cp eidb_country_wise_export/msme_country.csv .
```

---

## 3. StatVarGroup Hierarchy (NEW FILE)

Created `statvar_hierarchy.mcf` to make variables appear in the sidebar:

```mcf
# StatVarGroup hierarchy for EIDB Export Data
# This connects the statistical variables to the sidebar hierarchy

# Root group for EIDB data - connects to dc/g/Root (top level)
Node: dcid:dc/g/EIDB
typeOf: dcs:StatVarGroup
name: "India Export Data (EIDB)"
specializationOf: dcid:dc/g/Root

# Sub-group for commodity-wise exports
Node: dcid:dc/g/EIDB_CommodityExports
typeOf: dcs:StatVarGroup
name: "Commodity-wise Exports"
specializationOf: dcid:dc/g/EIDB

# Sub-group for country-wise exports
Node: dcid:dc/g/EIDB_CountryExports
typeOf: dcs:StatVarGroup
name: "Country-wise Exports"
specializationOf: dcid:dc/g/EIDB

# Sub-group for export percentages
Node: dcid:dc/g/EIDB_ExportPercentages
typeOf: dcs:StatVarGroup
name: "Export Percentages"
specializationOf: dcid:dc/g/EIDB

# Sub-group for growth rates
Node: dcid:dc/g/EIDB_GrowthRates
typeOf: dcs:StatVarGroup
name: "Export Growth Rates"
specializationOf: dcid:dc/g/EIDB
```

### Hierarchy Options:
- `specializationOf: dcid:dc/g/Root` - Appears at TOP LEVEL in sidebar
- `specializationOf: dcid:dc/g/Economy` - Appears under Economy category

---

## 4. Variable-to-Group Mapping (NEW FILE)

Created `statvar_memberof.mcf` to connect variables to their groups.

### Generation Script:
```python
#!/usr/bin/env python3
# gen_memberof.py - Generate memberOf statements for all variables

import sqlite3

# Connect to the database
conn = sqlite3.connect('datacommons/datacommons.db')
cursor = conn.cursor()

# Get all unique variables
cursor.execute("SELECT DISTINCT variable FROM observations")
variables = [row[0] for row in cursor.fetchall()]

mcf_lines = ["# Auto-generated memberOf statements for EIDB variables\n"]

for var in variables:
    # Assign to appropriate group based on variable name pattern
    if '_AsAFractionOf_' in var:
        group = 'dc/g/EIDB_ExportPercentages'
    elif var.startswith('GrowthRate_'):
        group = 'dc/g/EIDB_GrowthRates'
    elif 'ExportSourceIndia' in var:
        group = 'dc/g/EIDB_CountryExports'
    else:
        group = 'dc/g/EIDB_CommodityExports'

    mcf_lines.append(f"Node: dcid:{var}")
    mcf_lines.append(f"memberOf: dcid:{group}")
    mcf_lines.append("")

with open('statvar_memberof.mcf', 'w') as f:
    f.write('\n'.join(mcf_lines))

print(f"Generated memberOf statements for {len(variables)} variables")
conn.close()
```

### Sample Output:
```mcf
Node: dcid:Exports_EconomicActivity_AnimalsLive
memberOf: dcid:dc/g/EIDB_CommodityExports

Node: dcid:Exports_EconomicActivity_AnimalsLive_AsAFractionOf_Exports_EconomicActivity
memberOf: dcid:dc/g/EIDB_ExportPercentages

Node: dcid:GrowthRate_Exports_EconomicActivity_AnimalsLive
memberOf: dcid:dc/g/EIDB_GrowthRates

Node: dcid:Exports_EconomicActivity_ExportSourceIndia
memberOf: dcid:dc/g/EIDB_CountryExports
```

---

## 5. Sample Questions Update

Updated `server/config/home_page/sample_questions.json` for EIDB-relevant queries:

```json
[
  {
    "category": "India Exports",
    "questions": [
      "What are the top exports from India?",
      "Show me India's exports of textiles over time",
      "Which countries import the most from India?"
    ]
  },
  {
    "category": "Commodity Trade",
    "questions": [
      "What is India's pharmaceutical exports trend?",
      "Show exports of gems and jewellery from India",
      "How have India's petroleum exports changed?"
    ]
  },
  {
    "category": "Country-wise Trade",
    "questions": [
      "What does India export to the United States?",
      "Show India's exports to UAE over the years",
      "Which African countries import from India?"
    ]
  },
  {
    "category": "Export Growth",
    "questions": [
      "Which export commodities are growing fastest in India?",
      "Show export growth rates for machinery from India",
      "What is the growth in India's chemical exports?"
    ]
  },
  {
    "category": "Demographics",
    "questions": [
      "What is the population of India?",
      "Demographics around the world",
      "What is the age distribution in India?"
    ]
  },
  {
    "category": "Economy",
    "questions": [
      "What is the GDP of India?",
      "Tell me about the economy in India",
      "How does India's economy compare to other countries?"
    ]
  }
]
```

---

## 6. Docker Commands

### Step 1: Run Data Container
```bash
docker run --env-file custom_dc/env.list \
  -v /path/to/custom_dc:/path/to/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable
```

### Step 2: Run Services Container
```bash
docker run -d --name custom-dc \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v $(pwd)/custom_dc/:$(pwd)/custom_dc/ \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

### To Reload Data:
```bash
# 1. Stop services container
docker rm -f custom-dc

# 2. Clear existing data
rm -rf custom_dc/eidb/datacommons

# 3. Re-run data container
docker run --env-file custom_dc/env.list \
  -v /path/to/custom_dc:/path/to/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

# 4. Re-run services container
docker run -d --name custom-dc ...
```

---

## 7. Verification Commands

### Check observations loaded:
```bash
sqlite3 custom_dc/eidb/datacommons/datacommons.db "SELECT COUNT(*) FROM observations;"
# Expected: 30407
```

### Check triples loaded:
```bash
sqlite3 custom_dc/eidb/datacommons/datacommons.db "SELECT COUNT(*) FROM triples;"
# Expected: ~103000+
```

### Check hierarchy via API:
```bash
curl -s "http://localhost:8080/api/variable-group/info" \
  -X POST -H "Content-Type: application/json" \
  -d '{"dcid": "dc/g/EIDB"}'
```

### Check NL search:
```bash
curl "http://localhost:8080/api/nl/search-indicators?queries=exports%20India&limit_per_index=5"
```

---

## 8. Final File List

Files in `custom_dc/eidb/`:

| File | Purpose | Status |
|------|---------|--------|
| `config.json` | CSV import configuration | Modified |
| `consolidated_statvars.mcf` | StatisticalVariable definitions | Original |
| `hscodes.mcf` | HS Code entity definitions | Original |
| `msme_schema.mcf` | Schema definitions | Original |
| `statvar_hierarchy.mcf` | StatVarGroup hierarchy | **NEW** |
| `statvar_memberof.mcf` | Variable-to-group mapping | **NEW** |
| `msme_commodity_inr.csv` | Commodity export data (INR) | **MOVED** from subdirectory |
| `msme_country.csv` | Country-wise export data | **MOVED** from subdirectory |

---

## 9. Explore Page Queries

Queries that work with EIDB data:

- `exports from India`
- `India exports to USA`
- `tea exports India`
- `pharmaceutical exports India`
- `chemical exports from India`
- `textile exports India`

---

## 10. Key Learnings

1. **config.json is strict** - Only use documented fields (`provenance`, `format`, `columnMappings`)
2. **No subdirectory paths** - CSV files must be in the same directory as config.json
3. **No glob patterns** - Use explicit filenames
4. **Hierarchy requires MCF** - Variables need `memberOf` predicates to appear in sidebar
5. **Two-container workflow** - Always run data container before services container
6. **Provenances must match** - Every provenance in inputFiles must exist in sources section
