#!/usr/bin/env python3
"""
Test script for MCP tools via the proxy server.

Usage:
    python test_mcp_tools.py

Prerequisites:
    1. MCP server running: python3 -m uv tool run datacommons-mcp serve http --port 3000
    2. Proxy running: python3 additional_features/mcp_proxy_only.py
"""

import json
import requests
import sys

PROXY_URL = "http://localhost:5001"


def test_health():
    """Test proxy health endpoint."""
    print("\n" + "=" * 60)
    print("TEST: Health Check")
    print("=" * 60)
    try:
        response = requests.get(f"{PROXY_URL}/health", timeout=5)
        data = response.json()
        print(f"Status: {data.get('status')}")
        print(f"MCP URL: {data.get('mcp_url')}")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def test_list_tools():
    """Test listing available tools."""
    print("\n" + "=" * 60)
    print("TEST: List Tools")
    print("=" * 60)
    try:
        response = requests.get(f"{PROXY_URL}/api/tools", timeout=30)
        data = response.json()
        if data.get("success"):
            tools = data.get("tools", [])
            print(f"Found {len(tools)} tools:")
            for t in tools:
                print(f"  - {t.get('name')}")
            return tools
        else:
            print(f"FAILED: {data.get('error')}")
            return None
    except Exception as e:
        print(f"FAILED: {e}")
        return None


def call_tool(name: str, arguments: dict):
    """Call a tool and return the result."""
    try:
        response = requests.post(
            f"{PROXY_URL}/api/call",
            json={"name": name, "arguments": arguments},
            timeout=60
        )
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def test_search_indicators():
    """Test search_indicators tool."""
    print("\n" + "=" * 60)
    print("TEST: search_indicators")
    print("=" * 60)

    # Test 1: Search for population
    print("\nTest 1: Search for 'population' in 'California, USA'")
    result = call_tool("search_indicators", {
        "query": "population",
        "places": ["California, USA"]
    })

    if result.get("success"):
        content = result.get("result", {}).get("content", [])
        if content:
            text = content[0].get("text", "")
            # Parse and show summary
            try:
                data = json.loads(text)
                variables = data.get("variables", [])
                print(f"  Found {len(variables)} variables")
                if variables:
                    print(f"  First variable DCID: {variables[0].get('dcid')}")
                    places = variables[0].get("places_with_data", [])
                    print(f"  Places with data: {places[:3]}...")
                return True
            except:
                print(f"  Response: {text[:200]}...")
                return True
    else:
        print(f"  FAILED: {result.get('error')}")
        return False


def test_get_observations():
    """Test get_observations tool."""
    print("\n" + "=" * 60)
    print("TEST: get_observations")
    print("=" * 60)

    # Test 1: Get California population (correct parameters)
    print("\nTest 1: Get population of California (geoId/06)")
    result = call_tool("get_observations", {
        "variable_dcid": "Count_Person",
        "place_dcid": "geoId/06",
        "date": "latest"  # Important: specify date parameter
    })

    if result.get("success"):
        content = result.get("result", {}).get("content", [])
        if content:
            text = content[0].get("text", "")
            try:
                data = json.loads(text)
                observations = data.get("place_observations", [])
                if observations:
                    place = observations[0].get("place", {})
                    time_series = observations[0].get("time_series", [])
                    print(f"  Place: {place.get('name')} ({place.get('dcid')})")
                    if time_series:
                        latest = time_series[-1] if isinstance(time_series[-1], list) else time_series[-1]
                        print(f"  Latest data: {latest}")
                    return True
            except:
                print(f"  Response: {text[:300]}...")
                return True
    else:
        print(f"  FAILED: {result.get('error')}")

    # Test 2: Without date parameter (should default to 'latest')
    print("\nTest 2: Get population without explicit date")
    result = call_tool("get_observations", {
        "variable_dcid": "Count_Person",
        "place_dcid": "geoId/06"
    })

    if result.get("success"):
        print("  SUCCESS (default date handling works)")
        return True
    else:
        print(f"  FAILED: {result.get('error')}")
        return False


def test_get_observations_date_range():
    """Test get_observations with date range."""
    print("\n" + "=" * 60)
    print("TEST: get_observations with date range")
    print("=" * 60)

    # Correct way to specify date range
    print("\nTest: Get population from 2020-2023")
    result = call_tool("get_observations", {
        "variable_dcid": "Count_Person",
        "place_dcid": "geoId/06",
        "date": "range",
        "date_range_start": "2020",
        "date_range_end": "2023"
    })

    if result.get("success"):
        content = result.get("result", {}).get("content", [])
        if content:
            text = content[0].get("text", "")
            try:
                data = json.loads(text)
                observations = data.get("place_observations", [])
                if observations:
                    time_series = observations[0].get("time_series", [])
                    print(f"  Got {len(time_series)} data points")
                    for ts in time_series[:3]:
                        print(f"    {ts}")
                    return True
            except:
                print(f"  Response: {text[:300]}...")
                return True
    else:
        print(f"  FAILED: {result.get('error')}")
        return False


def main():
    print("=" * 60)
    print("MCP Tools Test Suite")
    print("=" * 60)
    print(f"Proxy URL: {PROXY_URL}")

    results = {}

    # Test health
    results["health"] = test_health()
    if not results["health"]:
        print("\nProxy not available. Make sure it's running!")
        sys.exit(1)

    # Test list tools
    tools = test_list_tools()
    results["list_tools"] = tools is not None

    if not tools:
        print("\nCouldn't list tools. Check MCP server!")
        sys.exit(1)

    # Test search_indicators
    results["search_indicators"] = test_search_indicators()

    # Test get_observations
    results["get_observations"] = test_get_observations()

    # Test get_observations with date range
    results["get_observations_range"] = test_get_observations_date_range()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {test}: {status}")

    all_passed = all(results.values())
    print("\n" + ("All tests passed!" if all_passed else "Some tests failed!"))
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
