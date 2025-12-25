# Custom Data Commons - Data Import Guide

This guide documents the complete process for transforming and importing new data into a Custom Data Commons instance.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Understanding the Working Format](#2-understanding-the-working-format)
3. [Step-by-Step Import Process](#3-step-by-step-import-process)
4. [Transformation Scripts](#4-transformation-scripts)
5. [Configuration Files](#5-configuration-files)
6. [Docker Commands](#6-docker-commands)
7. [Verification](#7-verification)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Prerequisites

### Required Files
- CSV file with observation data
- MCF file with StatisticalVariable definitions (optional but recommended)
- MCF file with schema definitions (optional)

### Directory Structure
All files must be in the root of your INPUT_DIR (e.g., `custom_dc/eidb/`):
```
custom_dc/eidb/
├── config.json                    # Configuration file
├── your_data.csv                  # CSV data file (in root, NOT subdirectory)
├── your_statvars.mcf              # Variable definitions
├── your_schema.mcf                # Schema definitions (optional)
├── statvar_hierarchy.mcf          # Group hierarchy
└── statvar_memberof.mcf           # Variable-to-group mapping
```

---

## 2. Understanding the Working Format

### Required CSV Format (variablePerRow)

```csv
observationAbout,observationDate,value,variableMeasured,unit,measurementMethod
country/IND,2020,2380100000,dcid:Exports_EconomicActivity_AnimalsLive,INR,ExportsInUSD
country/IND,2021,632400000,dcid:Exports_EconomicActivity_AnimalsLive,INR,ExportsInUSD
```

### Column Descriptions

| Column | Description | Example |
|--------|-------------|---------|
| `observationAbout` | Entity DCID | `country/IND`, `geoId/06` |
| `observationDate` | Year or date | `2020`, `2021-01` |
| `value` | Numeric value | `2380100000`, `0.5` |
| `variableMeasured` | Variable DCID | `dcid:MyVariable` or `MyVariable` |
| `unit` | Unit of measurement | `INR`, `USDollar`, `Percent` |
| `measurementMethod` | How it was measured | `ExportsInUSD`, `Census` |

### Common Format Issues

| Issue | Problem | Solution |
|-------|---------|----------|
| Extra columns | `typeOf` column present | Remove or ignore via transformation |
| Wrong column order | Columns in different order | Reorder or use columnMappings |
| Different column names | `entity` instead of `observationAbout` | Use columnMappings in config.json |
| Files in subdirectory | `subfolder/data.csv` | Move to root directory |

---

## 3. Step-by-Step Import Process

### Step 1: Analyze Source Data

```bash
# Check CSV structure
head -5 /path/to/source/data.csv

# Count rows
wc -l /path/to/source/data.csv

# Count unique variables
cut -d',' -f<variable_column> /path/to/source/data.csv | sort -u | wc -l
```

### Step 2: Transform CSV to Working Format

If your CSV doesn't match the working format, transform it:

```python
#!/usr/bin/env python3
# transform_csv.py

import csv

input_file = '/path/to/source/data.csv'
output_file = '/path/to/eidb/transformed_data.csv'

with open(input_file, 'r') as infile, open(output_file, 'w', newline='') as outfile:
    reader = csv.DictReader(infile)

    # Define output columns in correct order
    fieldnames = ['observationAbout', 'observationDate', 'value',
                  'variableMeasured', 'unit', 'measurementMethod']
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        new_row = {
            'observationAbout': row['observationAbout'],  # Map from source column
            'observationDate': row['observationDate'],
            'value': row['value'],
            'variableMeasured': row['variableMeasured'],
            'unit': row['unit'],
            'measurementMethod': 'YourMeasurementMethod'  # Add if missing
        }
        writer.writerow(new_row)

print(f"Transformed to: {output_file}")
```

### Step 3: Copy MCF Files to Root Directory

```bash
# Copy StatisticalVariable definitions
cp /path/to/source/statvars.mcf /path/to/eidb/your_statvars.mcf

# Copy schema definitions (if any)
cp /path/to/source/schema.mcf /path/to/eidb/your_schema.mcf
```

### Step 4: Update config.json

Add the new data source to config.json:

```json
{
  "inputFiles": {
    "existing_data.csv": {
      "provenance": "Existing Source",
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
    "new_data.csv": {
      "provenance": "New Data Source",
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
    "Your Organization": {
      "url": "https://your-source.org/",
      "provenances": {
        "Existing Source": "https://your-source.org/existing",
        "New Data Source": "https://your-source.org/new-data"
      }
    }
  }
}
```

### Step 5: Update StatVarGroup Hierarchy

Add a new group in `statvar_hierarchy.mcf` if needed:

```mcf
# Add new sub-group for your data
Node: dcid:dc/g/EIDB_NewCategory
typeOf: dcs:StatVarGroup
name: "New Category Name"
specializationOf: dcid:dc/g/EIDB
```

### Step 6: Generate memberOf Statements

Run script to generate memberOf predicates for all variables:

```python
#!/usr/bin/env python3
# gen_memberof.py

import csv

# Collect variables from all CSV files
all_variables = set()

csv_files = [
    '/path/to/eidb/existing_data.csv',
    '/path/to/eidb/new_data.csv'
]

for csv_file in csv_files:
    with open(csv_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            var = row['variableMeasured']
            if var.startswith('dcid:'):
                var = var[5:]
            all_variables.add(var)

print(f"Total variables: {len(all_variables)}")

# Generate memberOf statements
mcf_lines = ["# Auto-generated memberOf statements\n"]

for var in sorted(all_variables):
    # Determine group based on variable name pattern
    if '_AsAFractionOf_' in var:
        group = 'dc/g/EIDB_ExportPercentages'
    elif var.startswith('GrowthRate_'):
        group = 'dc/g/EIDB_GrowthRates'
    elif '_Country' in var and '_HSCode' in var:
        group = 'dc/g/EIDB_CountryCommodityExports'
    elif 'ExportSourceIndia' in var:
        group = 'dc/g/EIDB_CountryExports'
    else:
        group = 'dc/g/EIDB_CommodityExports'

    mcf_lines.append(f"Node: dcid:{var}")
    mcf_lines.append(f"memberOf: dcid:{group}")
    mcf_lines.append("")

with open('/path/to/eidb/statvar_memberof.mcf', 'w') as f:
    f.write('\n'.join(mcf_lines))

print("Generated statvar_memberof.mcf")
```

### Step 7: Clear Old Data and Reload

```bash
# Clear existing processed data
rm -rf /path/to/eidb/datacommons

# Run data container
docker run --env-file custom_dc/env.list \
  -v /path/to/custom_dc:/path/to/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

# Restart services container
docker rm -f custom-dc
docker run -d --name custom-dc \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v $(pwd)/custom_dc/:$(pwd)/custom_dc/ \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

---

## 4. Transformation Scripts

### Complete Transformation Script

Save as `scripts/transform_and_import.py`:

```python
#!/usr/bin/env python3
"""
Transform and prepare data for Custom Data Commons import.
Usage: python transform_and_import.py <source_csv> <output_name>
"""

import csv
import sys
import os

def transform_csv(source_file, output_dir, output_name):
    """Transform CSV to working format."""
    output_file = os.path.join(output_dir, f"{output_name}.csv")

    with open(source_file, 'r') as infile:
        reader = csv.DictReader(infile)
        source_columns = reader.fieldnames
        print(f"Source columns: {source_columns}")

        # Detect column mappings
        column_map = {}
        for col in source_columns:
            col_lower = col.lower()
            if 'about' in col_lower or col_lower == 'entity':
                column_map['observationAbout'] = col
            elif 'date' in col_lower:
                column_map['observationDate'] = col
            elif col_lower == 'value':
                column_map['value'] = col
            elif 'variable' in col_lower:
                column_map['variableMeasured'] = col
            elif col_lower == 'unit':
                column_map['unit'] = col
            elif 'method' in col_lower:
                column_map['measurementMethod'] = col

        print(f"Detected mappings: {column_map}")

        # Reset file pointer
        infile.seek(0)
        reader = csv.DictReader(infile)

        # Write transformed CSV
        fieldnames = ['observationAbout', 'observationDate', 'value',
                      'variableMeasured', 'unit', 'measurementMethod']

        with open(output_file, 'w', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()

            row_count = 0
            for row in reader:
                new_row = {
                    'observationAbout': row.get(column_map.get('observationAbout', ''), ''),
                    'observationDate': row.get(column_map.get('observationDate', ''), ''),
                    'value': row.get(column_map.get('value', ''), ''),
                    'variableMeasured': row.get(column_map.get('variableMeasured', ''), ''),
                    'unit': row.get(column_map.get('unit', ''), ''),
                    'measurementMethod': row.get(column_map.get('measurementMethod', ''), 'DefaultMethod')
                }
                writer.writerow(new_row)
                row_count += 1

    print(f"Transformed {row_count} rows to {output_file}")
    return output_file

def collect_variables(csv_files):
    """Collect all unique variables from CSV files."""
    variables = set()
    for csv_file in csv_files:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                var = row.get('variableMeasured', '')
                if var.startswith('dcid:'):
                    var = var[5:]
                if var:
                    variables.add(var)
    return variables

def generate_memberof(variables, output_file, group_rules):
    """Generate memberOf MCF file."""
    mcf_lines = ["# Auto-generated memberOf statements\n"]

    for var in sorted(variables):
        group = 'dc/g/EIDB_CommodityExports'  # Default
        for pattern, target_group in group_rules.items():
            if pattern in var:
                group = target_group
                break

        mcf_lines.append(f"Node: dcid:{var}")
        mcf_lines.append(f"memberOf: dcid:{group}")
        mcf_lines.append("")

    with open(output_file, 'w') as f:
        f.write('\n'.join(mcf_lines))

    print(f"Generated {len(variables)} memberOf statements to {output_file}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python transform_and_import.py <source_csv> <output_name>")
        sys.exit(1)

    source_csv = sys.argv[1]
    output_name = sys.argv[2]
    output_dir = os.path.dirname(source_csv) or '.'

    transform_csv(source_csv, output_dir, output_name)
```

---

## 5. Configuration Files

### Complete config.json Template

```json
{
  "inputFiles": {
    "data_file_1.csv": {
      "provenance": "Data Source 1",
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
    "data_file_2.csv": {
      "provenance": "Data Source 2",
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
    "Organization Name": {
      "url": "https://organization.org/",
      "provenances": {
        "Data Source 1": "https://organization.org/data1",
        "Data Source 2": "https://organization.org/data2"
      }
    }
  }
}
```

### Complete statvar_hierarchy.mcf Template

```mcf
# StatVarGroup hierarchy for your data

# Root group - appears at top level in sidebar
Node: dcid:dc/g/YourData
typeOf: dcs:StatVarGroup
name: "Your Data Category"
specializationOf: dcid:dc/g/Root

# Sub-group 1
Node: dcid:dc/g/YourData_Category1
typeOf: dcs:StatVarGroup
name: "Category 1"
specializationOf: dcid:dc/g/YourData

# Sub-group 2
Node: dcid:dc/g/YourData_Category2
typeOf: dcs:StatVarGroup
name: "Category 2"
specializationOf: dcid:dc/g/YourData

# Sub-group 3
Node: dcid:dc/g/YourData_Category3
typeOf: dcs:StatVarGroup
name: "Category 3"
specializationOf: dcid:dc/g/YourData
```

---

## 6. Docker Commands

### Quick Reference

```bash
# 1. Clear existing data
rm -rf custom_dc/eidb/datacommons

# 2. Run data container (processes CSV and MCF files)
docker run --env-file custom_dc/env.list \
  -v /full/path/to/custom_dc:/full/path/to/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

# 3. Stop existing services container
docker rm -f custom-dc

# 4. Start services container
docker run -d --name custom-dc \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v $(pwd)/custom_dc/:$(pwd)/custom_dc/ \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable

# 5. Check logs
docker logs custom-dc 2>&1 | tail -50
```

### One-Liner Reload Script

Save as `scripts/reload_data.sh`:

```bash
#!/bin/bash
set -e

echo "=== Clearing old data ==="
rm -rf custom_dc/eidb/datacommons

echo "=== Running data container ==="
docker run --env-file custom_dc/env.list \
  -v $(pwd)/custom_dc:$(pwd)/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

echo "=== Restarting services container ==="
docker rm -f custom-dc 2>/dev/null || true
docker run -d --name custom-dc \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v $(pwd)/custom_dc/:$(pwd)/custom_dc/ \
  -v $(pwd)/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable

echo "=== Waiting for container to start ==="
sleep 20

echo "=== Verifying ==="
curl -s "http://localhost:8080/api/variable-group/info" \
  -X POST -H "Content-Type: application/json" \
  -d '{"dcid": "dc/g/EIDB"}' | head -20

echo "=== Done! ==="
```

---

## 7. Verification

### Check Data Loaded

```bash
# Count observations
sqlite3 custom_dc/eidb/datacommons/datacommons.db \
  "SELECT COUNT(*) FROM observations;"

# Count triples
sqlite3 custom_dc/eidb/datacommons/datacommons.db \
  "SELECT COUNT(*) FROM triples;"

# Sample observations
sqlite3 custom_dc/eidb/datacommons/datacommons.db \
  "SELECT * FROM observations LIMIT 5;"

# Count unique variables
sqlite3 custom_dc/eidb/datacommons/datacommons.db \
  "SELECT COUNT(DISTINCT variable) FROM observations;"
```

### Check Hierarchy via API

```bash
# Check main group
curl -s "http://localhost:8080/api/variable-group/info" \
  -X POST -H "Content-Type: application/json" \
  -d '{"dcid": "dc/g/EIDB"}'

# Check sub-group
curl -s "http://localhost:8080/api/variable-group/info" \
  -X POST -H "Content-Type: application/json" \
  -d '{"dcid": "dc/g/EIDB_CommodityExports"}' | head -30
```

### Test Data Access

```bash
# Get time series for a variable
curl "http://localhost:8080/api/observations/series?entities=country/IND&variables=YOUR_VARIABLE"

# Search for variables
curl "http://localhost:8080/api/nl/search-indicators?queries=exports&limit_per_index=5"
```

### Check Import Report

```bash
cat custom_dc/eidb/datacommons/process/report.json
```

---

## 8. Troubleshooting

### CSV Not Being Imported

**Symptom:** `Found 0 csv files to import`

**Causes & Solutions:**
1. File in subdirectory → Move to root of INPUT_DIR
2. Invalid config fields → Remove `importType`, `entityType`
3. Provenance mismatch → Ensure provenance in inputFiles exists in sources

### Variables Not in Sidebar

**Symptom:** Data loads but variables don't appear in Statistical Variable Explorer

**Solution:**
1. Create `statvar_hierarchy.mcf` with StatVarGroup definitions
2. Create `statvar_memberof.mcf` with memberOf predicates for each variable
3. Reload data

### hasData is False

**Symptom:** Variables appear but show as grayed out

**Cause:** Variable DCID in MCF doesn't match CSV

**Solution:** Ensure variable names in CSV match MCF definitions exactly

### Container Can't Find Database

**Symptom:** `Cannot open sqlite database`

**Solution:** Run data container before services container

---

## Checklist for New Data Import

- [ ] Analyze source CSV format
- [ ] Transform CSV to working format (if needed)
- [ ] Move CSV to root of INPUT_DIR
- [ ] Copy MCF files to root of INPUT_DIR
- [ ] Update config.json with new inputFiles entry
- [ ] Update config.json sources with new provenance
- [ ] Update statvar_hierarchy.mcf with new group (if needed)
- [ ] Regenerate statvar_memberof.mcf with all variables
- [ ] Clear datacommons folder
- [ ] Run data container
- [ ] Restart services container
- [ ] Verify via API and UI

---

## Example: Adding country_wise_all_commodity_export

### Original Format
```csv
typeOf,observationDate,observationAbout,value,unit,variableMeasured
dcs:StatVarObservation,2020,country/IND,0,USDollar,dcid:Exports_EconomicActivity_CountryAUS_HSCode02
```

### Transformed Format
```csv
observationAbout,observationDate,value,variableMeasured,unit,measurementMethod
country/IND,2020,0,dcid:Exports_EconomicActivity_CountryAUS_HSCode02,USDollar,ExportsInUSD
```

### Files Created
- `country_commodity_export.csv` - Transformed data
- `country_commodity_statvars.mcf` - Variable definitions
- `country_commodity_schema.mcf` - Schema definitions

### config.json Entry Added
```json
"country_commodity_export.csv": {
  "provenance": "Country Commodity Export",
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
```

### Hierarchy Group Added
```mcf
Node: dcid:dc/g/EIDB_CountryCommodityExports
typeOf: dcs:StatVarGroup
name: "Country-Commodity Exports"
specializationOf: dcid:dc/g/EIDB
```

### Result
- 1,270 new observations
- 622 new variables
- New "Country-Commodity Exports" group in sidebar
