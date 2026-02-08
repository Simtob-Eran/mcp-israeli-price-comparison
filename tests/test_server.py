"""Tests for the MCP server API."""

import json

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self, client: TestClient):
        """Test root endpoint returns OK."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "service" in data

    def test_health_endpoint(self, client: TestClient):
        """Test health endpoint returns detailed status."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "1.1.0"
        assert "tools_count" in data


class TestToolsEndpoints:
    """Tests for tools listing endpoints."""

    def test_list_tools(self, client: TestClient):
        """Test listing all available tools."""
        response = client.get("/mcp/tools")

        assert response.status_code == 200
        data = response.json()
        assert "tools" in data
        assert len(data["tools"]) == 13

    def test_list_tools_has_required_fields(self, client: TestClient):
        """Test that tools have required fields."""
        response = client.get("/mcp/tools")
        tools = response.json()["tools"]

        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool

    def test_get_specific_tool(self, client: TestClient):
        """Test getting a specific tool definition."""
        response = client.get("/mcp/tools/web_search")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "web_search"
        assert "inputSchema" in data

    def test_get_nonexistent_tool(self, client: TestClient):
        """Test getting a non-existent tool returns 404."""
        response = client.get("/mcp/tools/nonexistent_tool")

        assert response.status_code == 404


class TestMCPEndpoint:
    """Tests for the main MCP endpoint."""

    def test_mcp_initialize(self, client: TestClient):
        """Test MCP initialize request."""
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "initialize",
                "params": {},
                "id": 1,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["jsonrpc"] == "2.0"
        assert "result" in data
        assert data["result"]["serverInfo"]["name"] == "price-comparison-mcp"

    def test_mcp_tools_list(self, client: TestClient):
        """Test MCP tools/list request."""
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert "tools" in data["result"]
        assert len(data["result"]["tools"]) == 13

    def test_mcp_invalid_method(self, client: TestClient):
        """Test MCP request with invalid method."""
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "invalid/method",
                "id": 3,
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == -32601

    def test_mcp_invalid_json(self, client: TestClient):
        """Test MCP request with invalid JSON."""
        response = client.post(
            "/mcp",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 400

    def test_mcp_tools_call_sse_headers(self, client: TestClient):
        """Test that tools/call returns SSE content type."""
        response = client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "parse_price",
                    "arguments": {"price_string": "₪100"},
                },
                "id": 4,
            },
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]


class TestMCPStreamEndpoint:
    """Tests for the SSE streaming endpoint."""

    def test_stream_endpoint_returns_sse(self, client: TestClient):
        """Test that stream endpoint returns SSE."""
        response = client.post(
            "/mcp/stream",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "parse_price",
                    "arguments": {"price_string": "₪500"},
                },
                "id": 1,
            },
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]

    def test_stream_endpoint_invalid_method(self, client: TestClient):
        """Test stream endpoint rejects non-tools/call methods."""
        response = client.post(
            "/mcp/stream",
            json={
                "jsonrpc": "2.0",
                "method": "tools/list",
                "id": 1,
            },
        )

        assert response.status_code == 200
        # Should contain error in SSE format
        assert b"error" in response.content

    def test_stream_endpoint_unknown_tool(self, client: TestClient):
        """Test stream endpoint handles unknown tool."""
        response = client.post(
            "/mcp/stream",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "unknown_tool",
                    "arguments": {},
                },
                "id": 1,
            },
        )

        assert response.status_code == 200
        assert b"error" in response.content


class TestRateLimiting:
    """Tests for rate limiting middleware."""

    def test_rate_limit_headers(self, client: TestClient):
        """Test that rate limit headers are present."""
        response = client.get("/mcp/tools")

        assert "X-RateLimit-Limit" in response.headers
        assert "X-RateLimit-Remaining" in response.headers

    def test_health_bypasses_rate_limit(self, client: TestClient):
        """Test that health check bypasses rate limiting."""
        # Make many requests to health endpoint
        for _ in range(150):
            response = client.get("/health")
            assert response.status_code == 200


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_headers_present(self, client: TestClient):
        """Test CORS headers on preflight request."""
        response = client.options(
            "/mcp",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )

        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
