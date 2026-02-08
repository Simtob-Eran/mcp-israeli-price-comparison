#!/usr/bin/env python3
"""Simple test script to test the MCP server at localhost:8000."""

import json
import sys

import httpx

MCP_BASE_URL = "http://localhost:8000"


def test_health():
    """Test health endpoint."""
    print("Testing /health...")
    try:
        response = httpx.get(f"{MCP_BASE_URL}/health", timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_list_tools_rest():
    """Test listing tools via REST endpoint."""
    print("\nTesting /mcp/tools (REST)...")
    try:
        response = httpx.get(f"{MCP_BASE_URL}/mcp/tools", timeout=10)
        print(f"Status: {response.status_code}")
        data = response.json()

        if "tools" in data:
            print(f"\nFound {len(data['tools'])} tools:")
            for tool in data["tools"]:
                print(f"  - {tool['name']}: {tool['description'][:60]}...")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_list_tools_mcp():
    """Test listing tools via MCP JSON-RPC endpoint."""
    print("\nTesting /mcp (MCP JSON-RPC tools/list)...")
    try:
        request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "params": {},
            "id": 1
        }
        response = httpx.post(
            f"{MCP_BASE_URL}/mcp",
            json=request,
            timeout=10
        )
        print(f"Status: {response.status_code}")
        data = response.json()

        if "result" in data and "tools" in data["result"]:
            print(f"\nFound {len(data['result']['tools'])} tools via MCP:")
            for tool in data["result"]["tools"]:
                print(f"  - {tool['name']}: {tool['description'][:60]}...")
        elif "error" in data:
            print(f"Error: {data['error']}")
        else:
            print(f"Response: {json.dumps(data, indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_mcp_initialize():
    """Test MCP initialize method."""
    print("\nTesting /mcp (MCP initialize)...")
    try:
        request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            },
            "id": 1
        }
        response = httpx.post(
            f"{MCP_BASE_URL}/mcp",
            json=request,
            timeout=10
        )
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False


def test_providers():
    """Test listing search providers."""
    print("\nTesting /mcp/providers...")
    try:
        response = httpx.get(f"{MCP_BASE_URL}/mcp/providers", timeout=10)
        print(f"Status: {response.status_code}")
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("MCP Server Test - localhost:8000")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Health Check", test_health()))
    results.append(("Providers", test_providers()))
    results.append(("REST Tools List", test_list_tools_rest()))
    results.append(("MCP Initialize", test_mcp_initialize()))
    results.append(("MCP Tools List", test_list_tools_mcp()))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = 0
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
        if result:
            passed += 1

    print(f"\nTotal: {passed}/{len(results)} tests passed")

    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
