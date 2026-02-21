# Centralized Log Collector Service

A Flask service that aggregates analytics from multiple MCP proxy servers and provides a unified dashboard for the AI India Summit.

## Features

- Aggregates logs from multiple data sources
- Auto-refreshes data every 30 seconds
- Shows queries from 16 Feb 7 AM IST (AI India Summit start)
- Displays:
  - Queries in last 24 hours with % change
  - Total queries, successful, failed, stopped counts
  - Top Stat Vars by successful queries (histogram)
  - Top Stat Vars by failed/stopped queries (histogram)
  - Queries by day chart
  - MCP tool usage
  - Response time percentiles
  - Recent queries table with search

## Deployment Instructions

### Option 1: Direct Python Deployment

1. **Clone/Copy the files to your server:**
   ```bash
   cd /path/to/deployment
   mkdir centralised_logs
   # Copy log_collector.py, config.json, requirements.txt
   ```

2. **Create a virtual environment:**
   ```bash
   cd centralised_logs
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure the service:**
   ```bash
   cp config.json.example config.json
   # Edit config.json with your source URLs and secret key
   nano config.json
   ```

5. **Run the service:**
   ```bash
   python log_collector.py
   ```

### Option 2: Systemd Service (Production)

1. **Complete steps 1-4 from Option 1**

2. **Create a systemd service file:**
   ```bash
   sudo nano /etc/systemd/system/log-collector.service
   ```

3. **Add the following content:**
   ```ini
   [Unit]
   Description=Centralized Log Collector Service
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/path/to/centralised_logs
   Environment="PATH=/path/to/centralised_logs/venv/bin"
   ExecStart=/path/to/centralised_logs/venv/bin/python log_collector.py
   Restart=always
   RestartSec=10

   [Install]
   WantedBy=multi-user.target
   ```

4. **Enable and start the service:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable log-collector
   sudo systemctl start log-collector
   ```

5. **Check status:**
   ```bash
   sudo systemctl status log-collector
   journalctl -u log-collector -f  # View logs
   ```

### Option 3: Google Cloud Run Deployment (Recommended)

1. **Make sure you have the files:**
   ```
   centralised_logs/
   ├── Dockerfile
   ├── log_collector.py
   ├── config.json
   ├── requirements.txt
   └── .dockerignore
   ```

2. **Build and push to Google Container Registry:**
   ```bash
   cd centralised_logs

   # Set your project ID
   export PROJECT_ID=your-gcp-project-id

   # Build the image
   gcloud builds submit --tag gcr.io/$PROJECT_ID/log-collector
   ```

3. **Deploy to Cloud Run:**
   ```bash
   gcloud run deploy log-collector \
     --image gcr.io/$PROJECT_ID/log-collector \
     --platform managed \
     --region asia-south1 \
     --allow-unauthenticated \
     --memory 512Mi \
     --cpu 1 \
     --min-instances 1 \
     --max-instances 3 \
     --timeout 300
   ```

4. **Access your dashboard:**
   ```
   https://log-collector-XXXXX-el.a.run.app/logs?key=AISummit2026
   ```

#### Cloud Run with Artifact Registry (Alternative)

```bash
# Create Artifact Registry repository (one-time)
gcloud artifacts repositories create log-collector \
  --repository-format=docker \
  --location=asia-south1

# Build and push
gcloud builds submit \
  --tag asia-south1-docker.pkg.dev/$PROJECT_ID/log-collector/log-collector

# Deploy
gcloud run deploy log-collector \
  --image asia-south1-docker.pkg.dev/$PROJECT_ID/log-collector/log-collector \
  --platform managed \
  --region asia-south1 \
  --allow-unauthenticated
```

### Option 4: Local Docker Deployment

1. **Build the image:**
   ```bash
   docker build -t log-collector .
   ```

2. **Run the container:**
   ```bash
   docker run -d -p 5003:5003 --name log-collector log-collector
   ```

3. **View logs:**
   ```bash
   docker logs -f log-collector
   ```

### Option 5: Using Screen/Tmux (Quick Deployment)

```bash
# Using screen
screen -S log-collector
source venv/bin/activate
python log_collector.py
# Press Ctrl+A, then D to detach

# To reattach
screen -r log-collector
```

## Configuration

Edit `config.json`:

```json
{
    "sources": [
        "http://server1:5001/api/logs/analytics?key=YOUR_KEY",
        "http://server2:5001/api/logs/analytics?key=YOUR_KEY"
    ],
    "secret_key": "YOUR_DASHBOARD_SECRET_KEY",
    "fetch_interval_seconds": 30,
    "port": 5003
}
```

| Field | Description |
|-------|-------------|
| `sources` | List of MCP proxy analytics API URLs |
| `secret_key` | Secret key required to access the dashboard |
| `fetch_interval_seconds` | How often to fetch from sources (default: 30) |
| `port` | Port to run the service on (default: 5003) |

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `/` | Service info (JSON) |
| `/health` | Health check endpoint |
| `/logs?key=SECRET` | HTML Dashboard |
| `/api/logs/analytics?key=SECRET` | JSON API for analytics data |

## Accessing the Dashboard

Once deployed, access the dashboard at:
```
http://YOUR_SERVER_IP:5003/logs?key=YOUR_SECRET_KEY
```

## Firewall Configuration

Make sure port 5003 (or your configured port) is open:

```bash
# Ubuntu/Debian
sudo ufw allow 5003

# CentOS/RHEL
sudo firewall-cmd --zone=public --add-port=5003/tcp --permanent
sudo firewall-cmd --reload

# GCP
gcloud compute firewall-rules create allow-log-collector \
    --allow tcp:5003 \
    --source-ranges 0.0.0.0/0 \
    --description "Allow log collector dashboard"
```

## Troubleshooting

1. **No data showing:**
   - Check if source URLs are accessible
   - Verify secret keys match
   - Check service logs: `journalctl -u log-collector -f`

2. **Service won't start:**
   - Check Python version (requires 3.8+)
   - Verify all dependencies installed
   - Check port is not in use: `lsof -i :5003`

3. **Data not updating:**
   - Verify background fetcher is running (check logs)
   - Ensure network connectivity to source servers
