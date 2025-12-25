# Custom Data Commons Docker Deployment Guide

This guide breaks down the `run_cdc_dev_docker.sh` script into manual commands you can run step-by-step.

## Prerequisites

- Docker installed and running
- GCP CLI installed (for cloud deployments)

## Step 1: Set Environment Variables

Run these in your terminal to set up the environment. Modify values as needed:

```bash
# Navigate to the website directory
cd /Users/saurabhgupta/Documents/2026/website

# Required: Data directories (use absolute paths)
export INPUT_DIR="/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/"
export OUTPUT_DIR="/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/"

# Required: API Key
export DC_API_KEY="your-dc-api-key"

# Optional: Maps API for place search
export MAPS_API_KEY=""

# Database settings
export USE_SQLITE="true"
export USE_CLOUDSQL="false"
export DB_NAME="datacommons"

# NL/Model settings
export ENABLE_MODEL="true"

# Flask environment (determines template directory)
export FLASK_ENV="custom"

# Release version: "stable" or "latest"
export RELEASE="stable"

# GCP settings (only needed for cloud upload)
export GOOGLE_CLOUD_PROJECT=""
export GOOGLE_CLOUD_REGION="us-central1"
```

## Step 2: Create Environment File

The Docker containers read from an env file. Create or verify `custom_dc/env.list`:

```bash
cat custom_dc/env.list
```

Or create a minimal one:

```bash
cat > custom_dc/env.list << 'EOF'
DC_API_KEY=your-dc-api-key
MAPS_API_KEY=
INPUT_DIR=/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/
OUTPUT_DIR=/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/
USE_SQLITE=true
USE_CLOUDSQL=false
DB_NAME=datacommons
ENABLE_MODEL=true
FLASK_ENV=custom
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_REGION=us-central1
EOF
```

---

## Deployment Options

### Option A: Run with Official Data Commons Images

#### A1. Pull the Images (Optional - Docker will auto-pull)

```bash
# Pull stable release
docker pull gcr.io/datcom-ci/datacommons-data:stable
docker pull gcr.io/datcom-ci/datacommons-services:stable

# Or pull latest release
docker pull gcr.io/datcom-ci/datacommons-data:latest
docker pull gcr.io/datcom-ci/datacommons-services:latest
```

#### A2. Run Data Container (Processes your CSV files)

This container reads your CSV + config.json, generates embeddings, and creates the SQLite database.

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  gcr.io/datcom-ci/datacommons-data:stable
```

**What this does:**
- Mounts your INPUT_DIR and OUTPUT_DIR into the container
- Processes CSV files according to config.json
- Generates NL embeddings (if ENABLE_MODEL=true)
- Creates SQLite database in OUTPUT_DIR

**Wait for this to complete before running the service container.**

#### A3. Run Service Container (Starts the Website)

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  -v /Users/saurabhgupta/Documents/2026/website/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v /Users/saurabhgupta/Documents/2026/website/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

**What this does:**
- Exposes port 8080 for web access
- Mounts your data directories
- Mounts your custom templates and static files for live editing
- Starts Flask website server

**Access at:** http://localhost:8080

---

### Option B: Run Service Container Only (Skip Data Processing)

Use this when your data hasn't changed:

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  -v /Users/saurabhgupta/Documents/2026/website/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v /Users/saurabhgupta/Documents/2026/website/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

---

### Option C: Build Custom Docker Image

#### C1. Build the Image

```bash
cd /Users/saurabhgupta/Documents/2026/website

docker build \
  --tag my-datacommons:dev \
  -f build/cdc_services/Dockerfile \
  .
```

**This takes several minutes.** It builds a custom image with your code changes baked in.

#### C2. Run Data Container with Custom Image

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  gcr.io/datcom-ci/datacommons-data:stable
```

#### C3. Run Service Container with Custom Image

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  -v /Users/saurabhgupta/Documents/2026/website/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v /Users/saurabhgupta/Documents/2026/website/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  my-datacommons:dev
```

---

### Option D: Upload Custom Image to Google Cloud

#### D1. Authenticate with GCP

```bash
# Login to GCP
gcloud auth login

# Set application default credentials
gcloud auth application-default login

# Configure Docker for Artifact Registry
gcloud auth configure-docker us-central1-docker.pkg.dev
```

#### D2. Set GCP Variables

```bash
export GOOGLE_CLOUD_PROJECT="your-project-id"
export GOOGLE_CLOUD_REGION="us-central1"
export IMAGE="my-datacommons:dev"
export PACKAGE="my-datacommons:dev"
```

#### D3. Tag the Image for Artifact Registry

```bash
docker tag ${IMAGE} \
  ${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${GOOGLE_CLOUD_PROJECT}-artifacts/${PACKAGE}
```

#### D4. Push to Artifact Registry

```bash
docker push \
  ${GOOGLE_CLOUD_REGION}-docker.pkg.dev/${GOOGLE_CLOUD_PROJECT}/${GOOGLE_CLOUD_PROJECT}-artifacts/${PACKAGE}
```

---

### Option E: Hybrid Mode - Data in Cloud, Service Local

When your OUTPUT_DIR is a GCS bucket:

#### E1. Set Environment for Hybrid

```bash
export INPUT_DIR="/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/"
export OUTPUT_DIR="gs://your-bucket/output/"
```

#### E2. Run Data Container (Writes to Cloud)

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -e GOOGLE_APPLICATION_CREDENTIALS=/gcp/creds.json \
  -v $HOME/.config/gcloud/application_default_credentials.json:/gcp/creds.json:ro \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  gcr.io/datcom-ci/datacommons-data:stable
```

#### E3. Run Service Container (Reads from Cloud)

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -e GOOGLE_APPLICATION_CREDENTIALS=/gcp/creds.json \
  -v $HOME/.config/gcloud/application_default_credentials.json:/gcp/creds.json:ro \
  -v /Users/saurabhgupta/Documents/2026/website/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v /Users/saurabhgupta/Documents/2026/website/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable
```

---

### Option F: Schema Update Mode (Fix SQL Errors)

If you encounter `SQL checked failed` errors:

```bash
docker run -it \
  --env-file custom_dc/env.list \
  -e DATA_UPDATE_MODE=schemaupdate \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  gcr.io/datcom-ci/datacommons-data:stable
```

This skips embeddings generation and only updates the database schema.

---

## Useful Docker Commands

### Check Running Containers

```bash
docker ps
```

### View Container Logs

```bash
docker logs -f <container_id>
```

### Stop a Container

```bash
docker stop <container_id>
```

### Remove Stopped Containers

```bash
docker container prune
```

### List Downloaded Images

```bash
docker images | grep datcom
```

### Remove Old Images

```bash
docker rmi gcr.io/datcom-ci/datacommons-data:stable
docker rmi gcr.io/datcom-ci/datacommons-services:stable
```

---

## Quick Copy-Paste Commands

### Minimal Local Setup (Most Common)

```bash
# Step 1: Navigate to project
cd /Users/saurabhgupta/Documents/2026/website

# Step 2: Run data container
docker run -it \
  --env-file custom_dc/env.list \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc:/Users/saurabhgupta/Documents/2026/website/custom_dc \
  gcr.io/datcom-ci/datacommons-data:stable

# Step 3: Run service container (in new terminal)
docker run -it \
  --env-file custom_dc/env.list \
  -p 8080:8080 \
  -e DEBUG=true \
  -v /Users/saurabhgupta/Documents/2026/website/custom_dc/sample/:/Users/saurabhgupta/Documents/2026/website/custom_dc/sample/ \
  -v /Users/saurabhgupta/Documents/2026/website/server/templates/custom_dc/custom:/workspace/server/templates/custom_dc/custom \
  -v /Users/saurabhgupta/Documents/2026/website/static/custom_dc/custom:/workspace/static/custom_dc/custom \
  gcr.io/datcom-ci/datacommons-services:stable

# Step 4: Open browser
open http://localhost:8080
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Port 8080 already in use | `docker stop $(docker ps -q)` or use `-p 8081:8080` |
| Permission denied | Run `gcloud auth application-default login` |
| Image not found | Run `docker pull gcr.io/datcom-ci/datacommons-services:stable` |
| Data not loading | Check INPUT_DIR path matches exactly in env.list and -v mount |
| SQL errors | Run with `-e DATA_UPDATE_MODE=schemaupdate` |
