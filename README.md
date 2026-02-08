# Unified Price Comparison MCP Server

A comprehensive Model Context Protocol (MCP) server with HTTP SSE (Server-Sent Events) transport that provides all tools needed for price comparison applications. Built with FastAPI and Python 3.11+.

## Features

- **MCP Protocol Support**: Full JSON-RPC 2.0 implementation with SSE streaming
- **Free Search Providers**: Uses DuckDuckGo, Google scraping, and Bing with smart fallback
- **10 Specialized Tools**: Web search, scraping, price intelligence, and data storage
- **Real-time Streaming**: Server-Sent Events for live progress updates
- **SQLite Storage**: Persistent price history and caching
- **Rate Limiting**: Built-in protection against API abuse
- **Docker Ready**: Production-ready containerization

## Quick Start

### Prerequisites

- Python 3.11+

### Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers (for JavaScript rendering)
playwright install chromium

# Configure environment
cp .env.example .env
```

### Running the Server

```bash
python main.py
```

The server will start at `http://localhost:8000`.

### Using Docker

```bash
# Build the image
docker build -t price-comparison-mcp .

# Run the container
docker run -p 8000:8000 price-comparison-mcp
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/health` | GET | Detailed health status |
| `/mcp/tools` | GET | List all available tools |
| `/mcp/tools/{name}` | GET | Get specific tool details |
| `/mcp/providers` | GET | List available search providers |
| `/mcp` | POST | MCP JSON-RPC endpoint (SSE) |
| `/mcp/stream` | POST | Streaming tool execution |
| `/docs` | GET | OpenAPI documentation |

## Available Tools

### Web Search Tools (Free Providers)

1. **web_search** - Web search with automatic fallback (DuckDuckGo, Google, Bing)
2. **shopping_search** - Product search with pricing data
3. **image_search** - Image search for visual product identification

### Web Scraping Tools

4. **fetch_page_content** - Fetch HTML from URLs (static or JS-rendered)
5. **extract_structured_data** - Extract JSON-LD, microdata, Open Graph
6. **extract_prices_from_html** - Multi-strategy price extraction

### Price Intelligence Tools

7. **parse_price** - Parse price strings to structured format
8. **normalize_product_name** - Normalize names with brand/model detection
9. **detect_product_specs** - Extract tech specs (memory, storage, etc.)
10. **calculate_total_cost** - Calculate total with shipping, tax, discounts

### Storage Tools

11. **save_search_result** - Save price findings to database
12. **get_price_history** - Retrieve historical price data
13. **get_average_market_price** - Calculate price statistics

## Usage Examples

### List Tools

```bash
curl http://localhost:8000/mcp/tools
```

### MCP Initialize

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "id": 1
  }'
```

### Call a Tool (with SSE streaming)

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "web_search",
      "arguments": {
        "query": "iPhone 15 Pro price Israel"
      }
    },
    "id": 2
  }'
```

### Python Client Example

```python
import httpx
import json

async def test_mcp_server():
    async with httpx.AsyncClient() as client:
        # List tools
        response = await client.get("http://localhost:8000/mcp/tools")
        print(response.json())

        # Call tool with SSE streaming
        async with client.stream(
            "POST",
            "http://localhost:8000/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": "shopping_search",
                    "arguments": {"query": "Samsung Galaxy S24"}
                },
                "id": 1
            }
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    print(data)

# Run with: asyncio.run(test_mcp_server())
```

## Configuration

Configuration is managed via environment variables. See `.env.example` for all options.

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | 0.0.0.0 | Server host |
| `PORT` | 8000 | Server port |
| `DATABASE_PATH` | database/prices.db | SQLite database path |
| `LOG_LEVEL` | INFO | Logging level |
| `RATE_LIMIT_REQUESTS` | 100 | Requests per window |
| `RATE_LIMIT_WINDOW` | 60 | Window duration (seconds) |

## Project Structure

```
.
├── src/
│   ├── server/
│   │   ├── main.py          # FastAPI + MCP server
│   │   ├── sse_handler.py   # SSE streaming logic
│   │   └── middleware.py    # CORS, logging, rate limiting
│   ├── tools/
│   │   ├── search_tools.py  # Search with free providers
│   │   ├── search_providers.py # DuckDuckGo, Google, Bing providers
│   │   ├── scraping_tools.py # Web scraping tools
│   │   ├── price_tools.py   # Price intelligence tools
│   │   └── storage_tools.py # SQLite storage tools
│   ├── models/
│   │   └── schemas.py       # Pydantic schemas
│   ├── utils/
│   │   ├── parser.py        # Price parsing
│   │   ├── normalizer.py    # Text normalization
│   │   └── database.py      # DB utilities
│   └── config/
│       └── settings.py      # Configuration
├── tests/
│   ├── test_tools.py        # Tool unit tests
│   ├── test_server.py       # API tests
│   └── test_integration.py  # Integration tests
├── database/
│   └── init.sql             # Database schema
├── main.py                  # Entry point
├── requirements.txt
├── Dockerfile
└── README.md
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_tools.py

# Run with verbose output
pytest -v
```

## Development

```bash
# Install dev dependencies
pip install -r requirements.txt

# Format code
black src tests
isort src tests

# Type checking
mypy src

# Linting
ruff check src tests
```

## SSE Event Format

Tool execution streams events in the following format:

```json
// Start event
data: {"type": "start", "tool": "web_search"}

// Progress event
data: {"type": "progress", "message": "Executing tool..."}

// Result event
data: {"type": "result", "data": {...}}

// Error event (if failed)
data: {"type": "error", "message": "Error description"}

// Complete event
data: {"type": "complete"}
```

## Database Schema

The SQLite database includes tables for:

- `search_results` - Price search results with product info
- `user_preferences` - User settings and preferences
- `price_alerts` - Price alert configurations
- `search_cache` - API response caching
- `api_usage` - Rate limit tracking

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
