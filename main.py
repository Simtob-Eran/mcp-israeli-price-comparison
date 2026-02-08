#!/usr/bin/env python3
"""Entry point for the Unified Price Comparison MCP Server.

This script starts the FastAPI server with MCP protocol support,
providing tools for web search, scraping, price intelligence, and data storage.

Usage:
    python main.py

Environment Variables:
    SERPER_API_KEY: API key for Serper (Google Search) integration
    HOST: Server host (default: 0.0.0.0)
    PORT: Server port (default: 8000)
    DEBUG: Enable debug mode (default: false)
    LOG_LEVEL: Logging level (default: INFO)

Example:
    SERPER_API_KEY=your_key python main.py
"""

import asyncio
import sys
from pathlib import Path

import uvicorn

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_settings
from src.server.main import app


def main() -> None:
    """Run the MCP server."""
    settings = get_settings()

    print(f"""
    ╔══════════════════════════════════════════════════════════════╗
    ║         Unified Price Comparison MCP Server                  ║
    ║                                                              ║
    ║  HTTP SSE Transport for Model Context Protocol               ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  Host: {settings.HOST:<52} ║
    ║  Port: {settings.PORT:<52} ║
    ║  Debug: {str(settings.DEBUG):<51} ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  Endpoints:                                                  ║
    ║    GET  /              - Health check                        ║
    ║    GET  /health        - Detailed health status              ║
    ║    GET  /mcp/tools     - List available tools                ║
    ║    POST /mcp           - MCP JSON-RPC endpoint (SSE)         ║
    ║    POST /mcp/stream    - Streaming tool execution            ║
    ║    GET  /docs          - OpenAPI documentation               ║
    ╠══════════════════════════════════════════════════════════════╣
    ║  Available Tools (13):                                       ║
    ║    - serper_search          - serper_shopping                ║
    ║    - serper_images          - fetch_page_content             ║
    ║    - extract_structured_data - extract_prices_from_html      ║
    ║    - parse_price            - normalize_product_name         ║
    ║    - detect_product_specs   - calculate_total_cost           ║
    ║    - save_search_result     - get_price_history              ║
    ║    - get_average_market_price                                ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.DEBUG,
    )


if __name__ == "__main__":
    main()
