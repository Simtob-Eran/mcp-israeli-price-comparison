# MCP Israeli Price Comparison

A comprehensive price comparison solution for the Israeli market, built on the Model Context Protocol (MCP).

## Project Overview

This repository contains a unified MCP server that provides all the tools needed for price comparison applications, including:

- **Web Search Integration**: Google search and shopping via Serper API
- **Web Scraping**: Static and JavaScript-rendered page fetching
- **Price Intelligence**: Price parsing, normalization, and analysis
- **Data Storage**: SQLite-based price history tracking

## Getting Started

See the [unified-mcp-server](./unified-mcp-server/) directory for the complete implementation.

```bash
cd unified-mcp-server
pip install -r requirements.txt
python main.py
```

## Architecture

The project uses HTTP with Server-Sent Events (SSE) for real-time streaming communication between clients and the MCP server.

## License

MIT
