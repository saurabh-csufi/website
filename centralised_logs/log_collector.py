#!/usr/bin/env python3
"""
Centralized Log Collector Service for AI India Summit Analytics Dashboard.

This service aggregates logs from multiple data sources and provides
a unified analytics dashboard.

Usage:
    python log_collector.py

Configuration:
    Edit config.json with your source endpoints and secret key.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests
from flask import Flask, jsonify, request, Response
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Global state for cached analytics
cached_analytics: Dict[str, Any] = {}
last_fetch_time: Optional[datetime] = None
fetch_lock = threading.Lock()

# AI India Summit start date: 16 Feb 2026, 7:00 AM IST
# IST is UTC+5:30, so 7:00 AM IST = 1:30 AM UTC
SUMMIT_START_DATE = datetime(2026, 2, 16, 1, 30, 0)  # UTC

# IST timezone offset: UTC+5:30
IST_OFFSET = timedelta(hours=5, minutes=30)


def get_ist_now() -> datetime:
    """Get current time in IST (Indian Standard Time = UTC+5:30)."""
    utc_now = datetime.now(timezone.utc)
    return utc_now + IST_OFFSET


def load_config() -> Dict[str, Any]:
    """Load configuration from environment variables or config.json.

    Environment variables (take priority over config.json):
        - LOG_COLLECTOR_SOURCES: Comma-separated list of source URLs
        - LOG_COLLECTOR_SECRET_KEY: Secret key for dashboard access
        - LOG_COLLECTOR_FETCH_INTERVAL: Fetch interval in seconds
        - PORT: Port to run on (Cloud Run sets this automatically)
    """
    # Start with defaults
    config = {
        "sources": [],
        "secret_key": "default",
        "fetch_interval_seconds": 30,
        "port": 5003
    }

    # Try to load from config.json
    config_path = Path(__file__).parent / 'config.json'
    try:
        with open(config_path, 'r') as f:
            file_config = json.load(f)
            config.update(file_config)
    except FileNotFoundError:
        logger.warning("config.json not found, using environment variables or defaults")
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config.json: {e}")

    # Override with environment variables if set
    if os.environ.get('LOG_COLLECTOR_SOURCES'):
        # Parse comma-separated URLs
        sources_str = os.environ['LOG_COLLECTOR_SOURCES']
        config['sources'] = [s.strip() for s in sources_str.split(',') if s.strip()]
        logger.info(f"Using sources from environment: {len(config['sources'])} sources")

    if os.environ.get('LOG_COLLECTOR_SECRET_KEY'):
        config['secret_key'] = os.environ['LOG_COLLECTOR_SECRET_KEY']
        logger.info("Using secret_key from environment")

    if os.environ.get('LOG_COLLECTOR_FETCH_INTERVAL'):
        try:
            config['fetch_interval_seconds'] = int(os.environ['LOG_COLLECTOR_FETCH_INTERVAL'])
        except ValueError:
            logger.warning("Invalid LOG_COLLECTOR_FETCH_INTERVAL, using default")

    return config


def fetch_from_source(url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """Fetch analytics data from a single source."""
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                return data
            else:
                logger.warning(f"Source {url} returned error: {data.get('error')}")
        else:
            logger.warning(f"Source {url} returned status {response.status_code}")
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching from {url}")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error fetching from {url}: {e}")
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON from {url}")
    return None


def filter_by_summit_date(data: Dict[str, Any]) -> Dict[str, Any]:
    """Filter data to only include entries from 16 Feb 7 AM IST onwards."""
    # Filter by_date to only include dates >= 2026-02-16
    if 'by_date' in data:
        filtered_by_date = {
            date: stats for date, stats in data['by_date'].items()
            if date >= '2026-02-16'
        }
        data['by_date'] = filtered_by_date

    # Filter recent_queries by timestamp
    if 'recent_queries' in data:
        filtered_queries = []
        for q in data['recent_queries']:
            if q.get('timestamp'):
                try:
                    # Parse timestamp and compare
                    ts = datetime.fromisoformat(q['timestamp'].replace('Z', '+00:00'))
                    if ts >= SUMMIT_START_DATE:
                        filtered_queries.append(q)
                except (ValueError, TypeError):
                    # If can't parse, include it
                    filtered_queries.append(q)
            else:
                filtered_queries.append(q)
        data['recent_queries'] = filtered_queries

    return data


def aggregate_analytics(sources_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate analytics from multiple sources."""
    if not sources_data:
        return {
            "total_queries": 0,
            "successful": 0,
            "failed": 0,
            "stopped": 0,
            "queries_24h": 0,
            "queries_24h_change": 0,
            "success_rate": 0,
            "response_times": {"avg_ms": 0, "p50": 0, "p75": 0, "p90": 0, "p95": 0, "p99": 0},
            "by_date": {},
            "mcp_summary": {"total_calls": 0, "by_tool": {}, "avg_per_query": 0},
            "stat_vars_successful": {},
            "stat_vars_failed": {},
            "recent_queries": [],
            "sources_count": 0,
            "generated_at": get_ist_now().isoformat()
        }

    # Initialize aggregated data
    total_queries = 0
    successful = 0
    failed = 0
    stopped = 0
    all_durations = []
    by_date: Dict[str, Dict[str, int]] = {}
    tool_counts: Dict[str, int] = {}
    total_tool_calls = 0
    stat_vars_successful: Dict[str, int] = {}
    stat_vars_failed: Dict[str, int] = {}
    all_recent_queries: List[Dict] = []

    for data in sources_data:
        # Filter by summit date first
        data = filter_by_summit_date(data)

        # Aggregate by_date (we'll calculate totals from this filtered data)
        for date, stats in data.get('by_date', {}).items():
            if date not in by_date:
                by_date[date] = {"queries": 0, "successful": 0, "failed": 0}
            by_date[date]["queries"] += stats.get("queries", 0)
            by_date[date]["successful"] += stats.get("successful", 0)
            by_date[date]["failed"] += stats.get("failed", 0)

    # Calculate totals from filtered by_date data (not from source totals)
    for date, stats in by_date.items():
        total_queries += stats.get("queries", 0)
        successful += stats.get("successful", 0)
        failed += stats.get("failed", 0)

    # Stopped = total - successful - failed (queries that were interrupted)
    stopped = total_queries - successful - failed

    # Second pass for other aggregations
    for data in sources_data:
        data = filter_by_summit_date(data)

        # Aggregate MCP tool counts
        mcp = data.get('mcp_summary', {})
        total_tool_calls += mcp.get('total_calls', 0)
        for tool, count in mcp.get('by_tool', {}).items():
            tool_counts[tool] = tool_counts.get(tool, 0) + count

        # Aggregate recent queries and extract stat vars by status
        for q in data.get('recent_queries', []):
            all_recent_queries.append(q)

            # Track stat vars by query status
            status = q.get('status', 'unknown')
            stat_vars = q.get('stat_vars', [])

            for sv in stat_vars:
                if status == 'success':
                    stat_vars_successful[sv] = stat_vars_successful.get(sv, 0) + 1
                elif status in ('failed', 'stopped'):
                    stat_vars_failed[sv] = stat_vars_failed.get(sv, 0) + 1

    # Calculate queries in last 24 hours and previous 24 hours for comparison
    # Use IST timezone for date calculations
    now_ist = get_ist_now()
    today_str = now_ist.strftime('%Y-%m-%d')
    yesterday_str = (now_ist - timedelta(days=1)).strftime('%Y-%m-%d')
    day_before_str = (now_ist - timedelta(days=2)).strftime('%Y-%m-%d')

    queries_24h = by_date.get(today_str, {}).get('queries', 0)
    # Add partial day queries if available
    if yesterday_str in by_date:
        # Approximate: add yesterday's queries weighted by time passed today (in IST)
        hour_fraction = now_ist.hour / 24
        queries_24h += int(by_date[yesterday_str].get('queries', 0) * (1 - hour_fraction))

    queries_prev_24h = by_date.get(yesterday_str, {}).get('queries', 0)
    if day_before_str in by_date:
        hour_fraction = now_ist.hour / 24
        queries_prev_24h += int(by_date[day_before_str].get('queries', 0) * hour_fraction)

    # Calculate percentage change
    if queries_prev_24h > 0:
        queries_24h_change = round(((queries_24h - queries_prev_24h) / queries_prev_24h) * 100, 1)
    else:
        queries_24h_change = 100 if queries_24h > 0 else 0

    # Sort recent queries by timestamp (most recent first)
    all_recent_queries.sort(key=lambda x: x.get('timestamp', '') or '', reverse=True)

    # Calculate response time stats from aggregated data
    # Since we don't have raw durations, use weighted averages from sources
    total_avg_ms = 0
    count_with_times = 0
    for data in sources_data:
        rt = data.get('response_times', {})
        if rt.get('avg_ms', 0) > 0:
            total_avg_ms += rt['avg_ms'] * data.get('total_queries', 1)
            count_with_times += data.get('total_queries', 1)

    avg_ms = total_avg_ms / count_with_times if count_with_times > 0 else 0

    # For percentiles, take the max across sources (conservative estimate)
    p50 = max((d.get('response_times', {}).get('p50', 0) for d in sources_data), default=0)
    p75 = max((d.get('response_times', {}).get('p75', 0) for d in sources_data), default=0)
    p90 = max((d.get('response_times', {}).get('p90', 0) for d in sources_data), default=0)
    p95 = max((d.get('response_times', {}).get('p95', 0) for d in sources_data), default=0)
    p99 = max((d.get('response_times', {}).get('p99', 0) for d in sources_data), default=0)

    # Sort stat vars by count (descending) and take top 10
    top_stat_vars_successful = dict(sorted(
        stat_vars_successful.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10])

    top_stat_vars_failed = dict(sorted(
        stat_vars_failed.items(),
        key=lambda x: x[1],
        reverse=True
    )[:10])

    return {
        "total_queries": total_queries,
        "successful": successful,
        "failed": failed,
        "stopped": stopped,
        "queries_24h": queries_24h,
        "queries_24h_change": queries_24h_change,
        "success_rate": round(successful / total_queries * 100, 1) if total_queries > 0 else 0,
        "response_times": {
            "avg_ms": round(avg_ms, 0),
            "p50": p50,
            "p75": p75,
            "p90": p90,
            "p95": p95,
            "p99": p99
        },
        "by_date": dict(sorted(by_date.items())),
        "mcp_summary": {
            "total_calls": total_tool_calls,
            "by_tool": tool_counts,
            "avg_per_query": round(total_tool_calls / total_queries, 1) if total_queries > 0 else 0
        },
        "stat_vars_successful": top_stat_vars_successful,
        "stat_vars_failed": top_stat_vars_failed,
        "recent_queries": all_recent_queries[:100],  # Limit to 100 most recent
        "sources_count": len(sources_data),
        "generated_at": get_ist_now().isoformat()
    }


def fetch_all_sources():
    """Fetch data from all configured sources and update cache."""
    global cached_analytics, last_fetch_time

    config = load_config()
    sources = config.get('sources', [])

    if not sources:
        logger.warning("No sources configured")
        return

    logger.info(f"Fetching from {len(sources)} sources...")

    # Fetch from all sources in parallel using threads
    results = []
    threads = []

    def fetch_and_store(url):
        data = fetch_from_source(url)
        if data:
            results.append(data)

    for url in sources:
        t = threading.Thread(target=fetch_and_store, args=(url,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=15)

    logger.info(f"Successfully fetched from {len(results)}/{len(sources)} sources")

    # Aggregate and cache
    with fetch_lock:
        cached_analytics = aggregate_analytics(results)
        last_fetch_time = datetime.now()


def background_fetcher():
    """Background thread that fetches data periodically."""
    config = load_config()
    interval = config.get('fetch_interval_seconds', 30)

    while True:
        try:
            fetch_all_sources()
        except Exception as e:
            logger.error(f"Error in background fetcher: {e}")
        time.sleep(interval)


# Start background fetcher thread
fetcher_thread = threading.Thread(target=background_fetcher, daemon=True)
fetcher_thread.start()


@app.route("/api/logs/analytics")
def logs_analytics():
    """API endpoint for aggregated logs analytics."""
    config = load_config()
    secret_key = request.args.get("key", "")
    expected_key = config.get("secret_key", "")

    if secret_key != expected_key:
        return jsonify({"error": "Invalid or missing key parameter"}), 401

    with fetch_lock:
        if cached_analytics:
            return jsonify({"success": True, **cached_analytics})
        else:
            return jsonify({"success": False, "error": "No data available yet. Please wait for initial fetch."})


@app.route("/logs")
def logs_dashboard():
    """HTML dashboard for centralized logs analytics."""
    config = load_config()
    secret_key = request.args.get("key", "")
    expected_key = config.get("secret_key", "")

    if secret_key != expected_key:
        return """
        <html>
        <head><title>Access Denied</title></head>
        <body style="background: #f8f9fa; color: #3C4043; font-family: 'Google Sans', system-ui, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
            <div style="text-align: center; background: white; padding: 40px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h1 style="color: #EA4335; margin-bottom: 16px;">Access Denied</h1>
                <p style="color: #5f6368;">Please provide a valid key parameter: /logs?key=YOUR_KEY</p>
            </div>
        </body>
        </html>
        """, 401

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>India Data Commons: AI Agent Analytics</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            /* Google Colors - Light Mode Theme */
            :root {{
                --google-blue: #4285F4;
                --google-red: #EA4335;
                --google-yellow: #FBBC04;
                --google-green: #34A853;
                --text-dark: #3C4043;
                --text-muted: #5f6368;
                --bg-light: #f8f9fa;
                --bg-white: #ffffff;
                --border-color: #dadce0;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                background: var(--bg-light);
                color: var(--text-dark);
                font-family: 'Google Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                padding: 20px;
                min-height: 100vh;
            }}
            .summit-banner {{
                background: linear-gradient(135deg, #FF9933 0%, #FFFFFF 50%, #138808 100%);
                color: #1a1a2e;
                padding: 16px 24px;
                border-radius: 12px;
                margin-bottom: 24px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .summit-banner h2 {{
                font-size: 18px;
                font-weight: 600;
                margin-bottom: 4px;
            }}
            .summit-banner p {{
                font-size: 13px;
                opacity: 0.8;
            }}
            .header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 24px;
                padding-bottom: 16px;
                border-bottom: 1px solid var(--border-color);
            }}
            .header h1 {{ font-size: 24px; color: var(--text-dark); }}
            .header-actions {{ display: flex; gap: 12px; align-items: center; }}
            .refresh-btn {{
                background: var(--google-blue);
                color: #fff;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
            }}
            .refresh-btn:hover {{ background: #3367d6; }}
            .auto-refresh {{ font-size: 12px; color: var(--text-muted); }}
            .last-updated {{ font-size: 12px; color: var(--text-muted); }}
            .sources-badge {{
                background: var(--google-green);
                color: white;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 12px;
            }}

            .cards {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }}
            .card {{
                background: var(--bg-white);
                border-radius: 12px;
                padding: 20px;
                border: 1px solid var(--border-color);
                box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            }}
            .card-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }}
            .card-value {{ font-size: 32px; font-weight: 700; color: var(--text-dark); margin: 8px 0; }}
            .card-sub {{ font-size: 14px; color: var(--text-muted); }}
            .card.success .card-value {{ color: var(--google-green); }}
            .card.error .card-value {{ color: var(--google-red); }}
            .card.warning .card-value {{ color: var(--google-yellow); }}
            .card.highlight {{
                background: linear-gradient(135deg, var(--google-blue) 0%, #5a9cf8 100%);
                color: white;
            }}
            .card.highlight .card-label {{ color: rgba(255,255,255,0.8); }}
            .card.highlight .card-value {{ color: white; }}
            .card.highlight .card-sub {{ color: rgba(255,255,255,0.9); }}
            .change-up {{ color: var(--google-green) !important; }}
            .change-down {{ color: var(--google-red) !important; }}

            .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin-bottom: 24px; }}
            @media (max-width: 1200px) {{ .grid {{ grid-template-columns: 1fr; }} }}

            .panel {{
                background: var(--bg-white);
                border-radius: 12px;
                padding: 20px;
                border: 1px solid var(--border-color);
                box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            }}
            .panel-title {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--text-dark); }}

            .chart-container {{ height: 250px; }}

            .tool-bar {{
                display: flex;
                align-items: center;
                margin-bottom: 8px;
            }}
            .tool-name {{
                width: 280px;
                font-size: 11px;
                color: var(--text-dark);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            .tool-progress {{
                flex: 1;
                height: 20px;
                background: #e8eaed;
                border-radius: 4px;
                overflow: hidden;
                margin: 0 12px;
            }}
            .tool-fill {{
                height: 100%;
                background: linear-gradient(90deg, var(--google-blue), #5a9cf8);
                border-radius: 4px;
            }}
            .tool-fill.success {{
                background: linear-gradient(90deg, var(--google-green), #45c362);
            }}
            .tool-fill.error {{
                background: linear-gradient(90deg, var(--google-red), #f87171);
            }}
            .tool-count {{ width: 60px; text-align: right; font-size: 13px; color: var(--text-muted); }}

            .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
            .stat-item {{ padding: 12px; background: var(--bg-light); border-radius: 8px; }}
            .stat-label {{ font-size: 11px; color: var(--text-muted); }}
            .stat-value {{ font-size: 18px; font-weight: 600; color: var(--text-dark); }}

            .table-container {{ overflow-x: auto; }}
            table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            th {{ text-align: left; padding: 12px 8px; border-bottom: 2px solid var(--border-color); color: var(--text-muted); font-weight: 500; }}
            td {{ padding: 12px 8px; border-bottom: 1px solid var(--border-color); }}
            tr:hover {{ background: var(--bg-light); }}
            .status-success {{ color: var(--google-green); font-weight: 600; }}
            .status-failed {{ color: var(--google-red); font-weight: 600; }}
            .status-stopped {{ color: var(--google-yellow); font-weight: 600; }}
            .stat-vars-cell {{ max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; color: var(--text-muted); }}
            .query-text {{ max-width: 350px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
            .expandable {{ cursor: pointer; }}
            .tool-details {{
                display: none;
                padding: 12px;
                background: var(--bg-light);
                margin: 4px 0;
                border-radius: 6px;
                font-size: 12px;
                border: 1px solid var(--border-color);
            }}
            .tool-details.show {{ display: block; }}
            .filter-row {{
                display: flex;
                gap: 12px;
                margin-bottom: 16px;
                flex-wrap: wrap;
                align-items: center;
            }}
            .search-box {{
                flex: 1;
                min-width: 200px;
                padding: 10px 14px;
                background: var(--bg-white);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                color: var(--text-dark);
                font-size: 14px;
            }}
            .search-box::placeholder {{ color: var(--text-muted); }}
            .search-box:focus {{ outline: none; border-color: var(--google-blue); box-shadow: 0 0 0 2px rgba(66,133,244,0.2); }}
            .date-input {{
                padding: 10px 14px;
                background: var(--bg-white);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                color: var(--text-dark);
                font-size: 14px;
            }}
            .date-input:focus {{ outline: none; border-color: var(--google-blue); box-shadow: 0 0 0 2px rgba(66,133,244,0.2); }}
            .filter-label {{ font-size: 12px; color: var(--text-muted); }}

            .percentile-bar {{
                display: flex;
                align-items: center;
                margin-bottom: 8px;
            }}
            .percentile-label {{ width: 50px; font-size: 12px; color: var(--text-muted); }}
            .percentile-track {{
                flex: 1;
                height: 24px;
                background: #e8eaed;
                border-radius: 4px;
                position: relative;
                overflow: hidden;
            }}
            .percentile-fill {{
                height: 100%;
                background: linear-gradient(90deg, var(--google-green), #45c362);
                border-radius: 4px;
                display: flex;
                align-items: center;
                justify-content: flex-end;
                padding-right: 8px;
                font-size: 11px;
                color: #fff;
                font-weight: 500;
            }}
        </style>
    </head>
    <body>
        <div class="summit-banner">
            <h2>All numbers are cumulative from 16 Feb (AI India Summit start date)</h2>
            <p>Data aggregated from multiple servers | Stats from 16 Feb 7:00 AM IST onwards</p>
        </div>

        <div class="header">
            <h1>India Data Commons: AI Agent Analytics</h1>
            <div class="header-actions">
                <span class="sources-badge" id="sourcesBadge">0 sources</span>
                <span class="last-updated" id="lastUpdated">Loading...</span>
                <label class="auto-refresh">
                    <input type="checkbox" id="autoRefresh" checked> Auto-refresh (30s)
                </label>
                <button class="refresh-btn" onclick="loadData()">Refresh</button>
            </div>
        </div>

        <div class="cards" id="summaryCards">
            <div class="card highlight">
                <div class="card-label">Last 24 Hours</div>
                <div class="card-value" id="queries24h">-</div>
                <div class="card-sub" id="queries24hChange">-</div>
            </div>
            <div class="card"><div class="card-label">Total Queries</div><div class="card-value" id="totalQueries">-</div></div>
            <div class="card success"><div class="card-label">Successful</div><div class="card-value" id="successful">-</div><div class="card-sub" id="successRate">-</div></div>
            <div class="card error"><div class="card-label">Failed</div><div class="card-value" id="failed">-</div></div>
            <div class="card warning"><div class="card-label">Stopped</div><div class="card-value" id="stopped">-</div></div>
            <div class="card"><div class="card-label">Avg Response</div><div class="card-value" id="avgTime">-</div><div class="card-sub">seconds</div></div>
        </div>

        <div class="panel" style="margin-bottom: 24px;">
            <div class="panel-title">Queries by Day (Since 16 Feb)</div>
            <div class="chart-container"><canvas id="dailyChart"></canvas></div>
        </div>

        <div class="grid">
            <div class="panel">
                <div class="panel-title">Top Stat Vars (Successful Queries)</div>
                <div id="statVarsSuccess"></div>
            </div>
            <div class="panel">
                <div class="panel-title">Top Stat Vars (Failed/Stopped Queries)</div>
                <div id="statVarsFailed"></div>
            </div>
        </div>

        <div class="grid">
            <div class="panel">
                <div class="panel-title">MCP Tool Usage</div>
                <div id="toolBars"></div>
                <div class="stats-grid" style="margin-top: 16px;">
                    <div class="stat-item"><div class="stat-label">Total Calls</div><div class="stat-value" id="totalCalls">-</div></div>
                    <div class="stat-item"><div class="stat-label">Avg per Query</div><div class="stat-value" id="avgCalls">-</div></div>
                </div>
            </div>
            <div class="panel">
                <div class="panel-title">Response Time Percentiles</div>
                <div id="percentileBars"></div>
            </div>
        </div>

        <div class="panel">
            <div class="panel-title">Recent Queries</div>
            <div class="filter-row">
                <input type="text" class="search-box" id="searchBox" placeholder="Search queries..." oninput="filterQueries()">
                <span class="filter-label">From:</span>
                <input type="date" class="date-input" id="dateFrom" onchange="filterQueries()">
                <span class="filter-label">To:</span>
                <input type="date" class="date-input" id="dateTo" onchange="filterQueries()">
                <button class="refresh-btn" onclick="clearDateFilter()" style="background: #5f6368;">Clear Dates</button>
            </div>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Date/Time (IST)</th>
                            <th>Query</th>
                            <th>Stat Vars</th>
                            <th>Status</th>
                            <th>Duration</th>
                            <th>Tools</th>
                        </tr>
                    </thead>
                    <tbody id="queriesTable"></tbody>
                </table>
            </div>
        </div>

        <script>
            const API_KEY = '{secret_key}';
            let analyticsData = null;
            let dailyChart = null;
            let autoRefreshInterval = null;

            // Convert UTC timestamp to IST (Indian Standard Time = UTC+5:30)
            function toIST(timestamp) {{
                if (!timestamp) return {{ display: '-', date: '' }};
                try {{
                    const utcDate = new Date(timestamp);
                    // Add 5 hours 30 minutes for IST
                    const istDate = new Date(utcDate.getTime() + (5.5 * 60 * 60 * 1000));
                    const display = istDate.toISOString().slice(0, 16).replace('T', ' ');
                    const date = istDate.toISOString().slice(0, 10); // YYYY-MM-DD for filtering
                    return {{ display, date }};
                }} catch (e) {{
                    return {{ display: timestamp.slice(0, 16).replace('T', ' '), date: timestamp.slice(0, 10) }};
                }}
            }}

            async function loadData() {{
                try {{
                    const res = await fetch('/api/logs/analytics?key=' + API_KEY);
                    const data = await res.json();
                    if (data.success) {{
                        analyticsData = data;
                        renderDashboard(data);
                        document.getElementById('lastUpdated').textContent = 'Updated: ' + new Date().toLocaleTimeString('en-IN', {{ timeZone: 'Asia/Kolkata' }});
                    }}
                }} catch (e) {{
                    console.error('Failed to load data:', e);
                }}
            }}

            function renderDashboard(data) {{
                // Sources badge
                document.getElementById('sourcesBadge').textContent = data.sources_count + ' sources';

                // 24h queries with change indicator
                document.getElementById('queries24h').textContent = data.queries_24h || 0;
                const change = data.queries_24h_change || 0;
                const changeEl = document.getElementById('queries24hChange');
                if (change > 0) {{
                    changeEl.innerHTML = '<span class="change-up">\u2191 ' + change + '% vs prev 24h</span>';
                }} else if (change < 0) {{
                    changeEl.innerHTML = '<span class="change-down">\u2193 ' + Math.abs(change) + '% vs prev 24h</span>';
                }} else {{
                    changeEl.textContent = 'No change vs prev 24h';
                }}

                // Summary cards
                document.getElementById('totalQueries').textContent = data.total_queries;
                document.getElementById('successful').textContent = data.successful;
                document.getElementById('successRate').textContent = data.success_rate + '% success';
                document.getElementById('failed').textContent = data.failed;
                document.getElementById('stopped').textContent = data.stopped || 0;
                document.getElementById('avgTime').textContent = (data.response_times.avg_ms / 1000).toFixed(1);

                // Daily chart
                renderDailyChart(data.by_date);

                // Stat vars histograms
                renderStatVarsBars('statVarsSuccess', data.stat_vars_successful, 'success');
                renderStatVarsBars('statVarsFailed', data.stat_vars_failed, 'error');

                // Tool bars
                renderToolBars(data.mcp_summary);
                document.getElementById('totalCalls').textContent = data.mcp_summary.total_calls;
                document.getElementById('avgCalls').textContent = data.mcp_summary.avg_per_query;

                // Percentile bars
                renderPercentileBars(data.response_times);

                // Queries table
                renderQueriesTable(data.recent_queries);
            }}

            // Google Colors
            const GOOGLE_COLORS = {{
                blue: '#4285F4',
                red: '#EA4335',
                yellow: '#FBBC05',
                green: '#34A853'
            }};

            function renderDailyChart(byDate) {{
                const labels = Object.keys(byDate);
                const successData = labels.map(d => byDate[d].successful);
                const failedData = labels.map(d => byDate[d].failed);

                const ctx = document.getElementById('dailyChart').getContext('2d');
                if (dailyChart) dailyChart.destroy();

                dailyChart = new Chart(ctx, {{
                    type: 'bar',
                    data: {{
                        labels: labels.map(d => d.slice(5)),
                        datasets: [
                            {{ label: 'Success', data: successData, backgroundColor: GOOGLE_COLORS.green }},
                            {{ label: 'Failed', data: failedData, backgroundColor: GOOGLE_COLORS.red }}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {{
                            x: {{ stacked: true, grid: {{ color: '#e8eaed' }}, ticks: {{ color: '#5f6368' }} }},
                            y: {{ stacked: true, grid: {{ color: '#e8eaed' }}, ticks: {{ color: '#5f6368' }} }}
                        }},
                        plugins: {{ legend: {{ labels: {{ color: '#5f6368' }} }} }}
                    }}
                }});
            }}

            function renderStatVarsBars(containerId, statVars, type) {{
                const container = document.getElementById(containerId);
                const entries = Object.entries(statVars || {{}});

                if (entries.length === 0) {{
                    container.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">No data available</p>';
                    return;
                }}

                const maxCount = Math.max(...entries.map(e => e[1]));

                container.innerHTML = entries
                    .map(([name, count]) => `
                        <div class="tool-bar">
                            <span class="tool-name" title="${{name}}">${{name}}</span>
                            <div class="tool-progress">
                                <div class="tool-fill ${{type}}" style="width: ${{count / maxCount * 100}}%"></div>
                            </div>
                            <span class="tool-count">${{count}}</span>
                        </div>
                    `).join('');
            }}

            function renderToolBars(mcpSummary) {{
                const container = document.getElementById('toolBars');
                const entries = Object.entries(mcpSummary.by_tool || {{}});

                if (entries.length === 0) {{
                    container.innerHTML = '<p style="color: var(--text-muted); font-size: 13px;">No tool usage data</p>';
                    return;
                }}

                const maxCount = Math.max(...entries.map(e => e[1]));

                container.innerHTML = entries
                    .sort((a, b) => b[1] - a[1])
                    .map(([name, count]) => `
                        <div class="tool-bar">
                            <span class="tool-name">${{name}}</span>
                            <div class="tool-progress">
                                <div class="tool-fill" style="width: ${{count / maxCount * 100}}%"></div>
                            </div>
                            <span class="tool-count">${{count}} calls</span>
                        </div>
                    `).join('');
            }}

            function renderPercentileBars(times) {{
                const container = document.getElementById('percentileBars');
                const maxTime = times.p99 || 1;
                const percentiles = ['p50', 'p75', 'p90', 'p95', 'p99'];

                container.innerHTML = percentiles.map(p => `
                    <div class="percentile-bar">
                        <span class="percentile-label">${{p}}</span>
                        <div class="percentile-track">
                            <div class="percentile-fill" style="width: ${{(times[p] / maxTime * 100)}}%">
                                ${{(times[p] / 1000).toFixed(1)}}s
                            </div>
                        </div>
                    </div>
                `).join('');
            }}

            function renderQueriesTable(queries) {{
                const tbody = document.getElementById('queriesTable');
                tbody.innerHTML = queries.map((q, i) => {{
                    let statusClass = 'status-stopped';
                    let statusSymbol = '\u23F9';
                    if (q.status === 'success') {{
                        statusClass = 'status-success';
                        statusSymbol = '\u2713';
                    }} else if (q.status === 'failed') {{
                        statusClass = 'status-failed';
                        statusSymbol = '\u2717';
                    }}
                    // Format stat vars for display
                    const statVars = q.stat_vars || [];
                    const statVarsDisplay = statVars.length > 0
                        ? statVars.slice(0, 2).join(', ') + (statVars.length > 2 ? ` (+${{statVars.length - 2}})` : '')
                        : '-';
                    const statVarsTitle = statVars.join('\\n');
                    // Convert timestamp to IST
                    const ist = toIST(q.timestamp);
                    // Store IST date for filtering
                    q._istDate = ist.date;
                    return `
                    <tr class="expandable" onclick="toggleDetails(${{i}})">
                        <td>${{ist.display}}</td>
                        <td class="query-text" title="${{q.full_query || ''}}">${{q.query || '-'}}</td>
                        <td class="stat-vars-cell" title="${{statVarsTitle}}">${{statVarsDisplay}}</td>
                        <td class="${{statusClass}}">${{statusSymbol}}</td>
                        <td>${{q.duration_ms ? (q.duration_ms / 1000).toFixed(1) + 's' : '-'}}</td>
                        <td>${{q.tool_count || 0}}</td>
                    </tr>
                    <tr><td colspan="6">
                        <div class="tool-details" id="details-${{i}}">
                            <strong>Session:</strong> ${{q.session_id}}<br>
                            <strong>Model:</strong> ${{q.model || 'unknown'}}<br>
                            <strong>KB Enabled:</strong> ${{q.kb_enabled ? 'Yes' : 'No'}}<br>
                            <strong>Stat Vars:</strong> ${{statVars.length > 0 ? statVars.join(', ') : 'None'}}<br>
                            <strong>Tools:</strong> ${{q.tool_calls ? q.tool_calls.map(t => t.name).join(', ') : 'None'}}
                        </div>
                    </td></tr>
                `}}).join('');
            }}

            function toggleDetails(idx) {{
                const el = document.getElementById('details-' + idx);
                el.classList.toggle('show');
            }}

            function filterQueries() {{
                const search = document.getElementById('searchBox').value.toLowerCase();
                const dateFrom = document.getElementById('dateFrom').value;
                const dateTo = document.getElementById('dateTo').value;

                if (!analyticsData) return;

                const filtered = analyticsData.recent_queries.filter(q => {{
                    // Text search filter
                    const matchesSearch = !search ||
                        (q.query && q.query.toLowerCase().includes(search)) ||
                        (q.session_id && q.session_id.toLowerCase().includes(search)) ||
                        (q.stat_vars && q.stat_vars.some(sv => sv.toLowerCase().includes(search)));

                    // Date filter (using IST converted date)
                    let matchesDate = true;
                    if (q.timestamp) {{
                        const ist = toIST(q.timestamp);
                        const queryDateIST = ist.date; // YYYY-MM-DD in IST
                        if (dateFrom && queryDateIST < dateFrom) {{
                            matchesDate = false;
                        }}
                        if (dateTo && queryDateIST > dateTo) {{
                            matchesDate = false;
                        }}
                    }}

                    return matchesSearch && matchesDate;
                }});

                renderQueriesTable(filtered);
            }}

            function clearDateFilter() {{
                document.getElementById('dateFrom').value = '';
                document.getElementById('dateTo').value = '';
                filterQueries();
            }}

            // Auto-refresh logic
            function setupAutoRefresh() {{
                const checkbox = document.getElementById('autoRefresh');

                function updateRefresh() {{
                    if (autoRefreshInterval) {{
                        clearInterval(autoRefreshInterval);
                        autoRefreshInterval = null;
                    }}
                    if (checkbox.checked) {{
                        autoRefreshInterval = setInterval(loadData, 30000);
                    }}
                }}

                checkbox.addEventListener('change', updateRefresh);
                updateRefresh();
            }}

            // Initial load
            loadData();
            setupAutoRefresh();
        </script>
    </body>
    </html>
    """


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "last_fetch": last_fetch_time.isoformat() if last_fetch_time else None,
        "cached_data_available": bool(cached_analytics)
    })


@app.route("/")
def index():
    """Root endpoint with service info."""
    config = load_config()
    return jsonify({
        "service": "Centralized Log Collector",
        "description": "AI India Summit Analytics Aggregator",
        "endpoints": {
            "/logs": "HTML Dashboard (requires ?key=SECRET_KEY)",
            "/api/logs/analytics": "JSON API (requires ?key=SECRET_KEY)",
            "/health": "Health check"
        },
        "sources_configured": len(config.get('sources', [])),
        "fetch_interval": config.get('fetch_interval_seconds', 30)
    })


if __name__ == "__main__":
    config = load_config()
    # Cloud Run sets PORT env var, fallback to config or 5003
    port = int(os.environ.get('PORT', config.get('port', 5003)))

    logger.info(f"Starting Centralized Log Collector on port {port}")
    logger.info(f"Configured sources: {len(config.get('sources', []))}")
    logger.info(f"Fetch interval: {config.get('fetch_interval_seconds', 30)} seconds")

    # Initial fetch
    fetch_all_sources()

    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
