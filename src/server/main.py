"""Main FastAPI application with MCP server integration."""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from mcp.server import Server
from mcp.types import Tool, TextContent

from ..config import get_settings
from ..models.schemas import MCPRequest, ToolDefinition
from ..tools import (
    calculate_total_cost,
    detect_product_specs,
    extract_prices_from_html,
    extract_structured_data,
    fetch_page_content,
    get_average_market_price,
    get_available_providers,
    get_price_history,
    image_search,
    normalize_product_name,
    parse_price,
    save_search_result,
    shopping_search,
    web_search,
)
from ..utils.database import get_database
from .middleware import setup_logging, setup_middleware
from .sse_handler import SSEHandler, stream_tool_result

logger = logging.getLogger(__name__)

# MCP Server instance
mcp_server = Server("price-comparison-mcp")

# Tool registry mapping tool names to their implementations
TOOL_REGISTRY: Dict[str, Any] = {
    # Search tools (with fallback support)
    "web_search": web_search,
    "shopping_search": shopping_search,
    "image_search": image_search,
    # Scraping tools
    "fetch_page_content": fetch_page_content,
    "extract_structured_data": extract_structured_data,
    "extract_prices_from_html": extract_prices_from_html,
    # Price tools
    "parse_price": parse_price,
    "normalize_product_name": normalize_product_name,
    "detect_product_specs": detect_product_specs,
    "calculate_total_cost": calculate_total_cost,
    # Storage tools
    "save_search_result": save_search_result,
    "get_price_history": get_price_history,
    "get_average_market_price": get_average_market_price,
}

# Tool definitions for MCP protocol
TOOL_DEFINITIONS: List[ToolDefinition] = [
    # Search Tools (with smart fallback)
    ToolDefinition(
        name="web_search",
        description="Perform web search with automatic fallback to free providers. Tries: Serper API (if key exists), DuckDuckGo, Google scraping, Bing scraping.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query string"},
                "num_results": {"type": "integer", "default": 10, "description": "Number of results (1-100)"},
                "country": {"type": "string", "default": "il", "description": "Country code for localized results"},
                "language": {"type": "string", "default": "he", "description": "Language code"},
                "use_cache": {"type": "boolean", "default": True, "description": "Use cached results if available"},
                "preferred_providers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred provider order: serper, duckduckgo, google_scraper, bing_scraper",
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="shopping_search",
        description="Search for products with prices. Automatic fallback: Serper Shopping, Google Shopping scraping, DuckDuckGo, Bing.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Product search query"},
                "num_results": {"type": "integer", "default": 20, "description": "Number of results (1-100)"},
                "country": {"type": "string", "default": "il", "description": "Country code"},
                "language": {"type": "string", "default": "he", "description": "Language code"},
                "use_cache": {"type": "boolean", "default": True, "description": "Use cached results if available"},
                "preferred_providers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred provider order",
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="image_search",
        description="Search for images with automatic fallback to free providers.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Image search query"},
                "num_results": {"type": "integer", "default": 10, "description": "Number of results (1-100)"},
                "country": {"type": "string", "default": "il", "description": "Country code"},
                "language": {"type": "string", "default": "he", "description": "Language code"},
                "use_cache": {"type": "boolean", "default": True, "description": "Use cached results if available"},
                "preferred_providers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Preferred provider order",
                },
            },
            "required": ["query"],
        },
    ),
    # Scraping Tools
    ToolDefinition(
        name="fetch_page_content",
        description="Fetch HTML content of a web page. Supports static and JavaScript-rendered pages.",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Target URL to fetch"},
                "render_js": {"type": "boolean", "default": False, "description": "Use Playwright for JS rendering"},
                "timeout": {"type": "integer", "default": 30, "description": "Request timeout in seconds"},
                "follow_redirects": {"type": "boolean", "default": True, "description": "Follow HTTP redirects"},
            },
            "required": ["url"],
        },
    ),
    ToolDefinition(
        name="extract_structured_data",
        description="Extract structured data from HTML including JSON-LD, microdata, Open Graph, and meta tags.",
        inputSchema={
            "type": "object",
            "properties": {
                "html": {"type": "string", "description": "HTML content to parse"},
                "data_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types to extract: json-ld, microdata, opengraph, meta",
                },
            },
            "required": ["html"],
        },
    ),
    ToolDefinition(
        name="extract_prices_from_html",
        description="Extract all prices from HTML using multiple strategies (structured data, selectors, regex).",
        inputSchema={
            "type": "object",
            "properties": {
                "html": {"type": "string", "description": "HTML content to parse"},
                "currency_hints": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Currency symbols/codes to look for",
                },
            },
            "required": ["html"],
        },
    ),
    # Price Tools
    ToolDefinition(
        name="parse_price",
        description="Parse price string to structured format. Handles various international formats.",
        inputSchema={
            "type": "object",
            "properties": {
                "price_string": {"type": "string", "description": "Price string to parse (e.g., '₪1,234.56')"},
                "currency_hint": {"type": "string", "description": "Optional currency code if not detectable"},
            },
            "required": ["price_string"],
        },
    ),
    ToolDefinition(
        name="normalize_product_name",
        description="Normalize product name for comparison. Extracts brand, model, and category hints.",
        inputSchema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Original product name"},
                "remove_stopwords": {"type": "boolean", "default": True, "description": "Remove common stopwords"},
            },
            "required": ["product_name"],
        },
    ),
    ToolDefinition(
        name="detect_product_specs",
        description="Extract technical specifications from text (memory, storage, display, processor, color, size).",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text containing specifications"},
                "spec_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types of specs to extract",
                },
            },
            "required": ["text"],
        },
    ),
    ToolDefinition(
        name="calculate_total_cost",
        description="Calculate total cost including base price, shipping, tax, discounts, and additional fees.",
        inputSchema={
            "type": "object",
            "properties": {
                "base_price": {"type": "number", "description": "Base product price"},
                "shipping_cost": {"type": "number", "default": 0, "description": "Shipping cost"},
                "tax_rate": {"type": "number", "default": 0, "description": "Tax rate as decimal (e.g., 0.17)"},
                "currency": {"type": "string", "default": "ILS", "description": "Currency code"},
                "discount_percent": {"type": "number", "default": 0, "description": "Discount percentage (0-100)"},
                "additional_fees": {
                    "type": "object",
                    "description": "Additional fees as {name: amount}",
                },
            },
            "required": ["base_price"],
        },
    ),
    # Storage Tools
    ToolDefinition(
        name="save_search_result",
        description="Save price search result to database for history tracking.",
        inputSchema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Product name"},
                "url": {"type": "string", "description": "URL where price was found"},
                "price": {"type": "number", "description": "Price value"},
                "currency": {"type": "string", "description": "Currency code"},
                "shipping_cost": {"type": "number", "description": "Shipping cost"},
                "availability": {"type": "string", "description": "Availability status"},
                "store_name": {"type": "string", "description": "Store name"},
                "metadata": {"type": "object", "description": "Additional metadata"},
            },
            "required": ["product_name", "url", "price", "currency"],
        },
    ),
    ToolDefinition(
        name="get_price_history",
        description="Retrieve historical price data for a product.",
        inputSchema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Product name to search for"},
                "days": {"type": "integer", "default": 30, "description": "Number of days to look back"},
                "limit": {"type": "integer", "default": 100, "description": "Maximum results"},
            },
            "required": ["product_name"],
        },
    ),
    ToolDefinition(
        name="get_average_market_price",
        description="Calculate average market price statistics for a product.",
        inputSchema={
            "type": "object",
            "properties": {
                "product_name": {"type": "string", "description": "Product name"},
                "days": {"type": "integer", "default": 7, "description": "Days to include in analysis"},
            },
            "required": ["product_name"],
        },
    ),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.

    Args:
        app: FastAPI application instance.
    """
    # Startup
    setup_logging()
    logger.info("Starting Price Comparison MCP Server")

    # Log available search providers
    providers = get_available_providers()
    logger.info(f"Available search providers: {', '.join(providers)}")

    # Initialize database
    db = await get_database()
    logger.info("Database initialized")

    yield

    # Shutdown
    logger.info("Shutting down Price Comparison MCP Server")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="Unified Price Comparison MCP Server",
        description="MCP server providing tools for web search, scraping, price intelligence, and data storage. Supports multiple free search providers with automatic fallback.",
        version="1.1.0",
        lifespan=lifespan,
    )

    # Setup middleware
    setup_middleware(app)

    # Register routes
    register_routes(app)

    return app


def register_routes(app: FastAPI) -> None:
    """Register all API routes.

    Args:
        app: FastAPI application instance.
    """

    @app.get("/")
    async def root():
        """Health check endpoint."""
        return {"status": "ok", "service": "price-comparison-mcp"}

    @app.get("/health")
    async def health():
        """Detailed health check."""
        providers = get_available_providers()
        return {
            "status": "healthy",
            "service": "price-comparison-mcp",
            "version": "1.1.0",
            "tools_count": len(TOOL_DEFINITIONS),
            "search_providers": providers,
        }

    @app.get("/mcp/providers")
    async def list_providers():
        """List available search providers.

        Returns:
            List of available search provider names.
        """
        return {
            "providers": get_available_providers(),
            "fallback_order": ["serper", "duckduckgo", "google_scraper", "bing_scraper"],
        }

    @app.get("/mcp/tools")
    async def list_tools():
        """List all available MCP tools.

        Returns:
            List of tool definitions with schemas.
        """
        return {
            "tools": [tool.model_dump() for tool in TOOL_DEFINITIONS],
        }

    @app.get("/mcp/tools/{tool_name}")
    async def get_tool(tool_name: str):
        """Get details for a specific tool.

        Args:
            tool_name: Name of the tool.

        Returns:
            Tool definition or 404 error.
        """
        for tool in TOOL_DEFINITIONS:
            if tool.name == tool_name:
                return tool.model_dump()

        return JSONResponse(
            status_code=404,
            content={"error": f"Tool '{tool_name}' not found"},
        )

    @app.post("/mcp")
    async def mcp_endpoint(request: Request):
        """MCP over HTTP with Server-Sent Events streaming.

        Accepts JSON-RPC requests and streams responses via SSE.
        Supports MCP protocol methods including tools/list and tools/call.

        Args:
            request: FastAPI request object.

        Returns:
            StreamingResponse with SSE events.
        """
        try:
            body = await request.json()
            mcp_request = MCPRequest(**body)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                    "id": None,
                },
            )

        # Handle different MCP methods
        if mcp_request.method == "tools/list":
            return await handle_tools_list(mcp_request)

        elif mcp_request.method == "tools/call":
            return await handle_tools_call(mcp_request)

        elif mcp_request.method == "initialize":
            return await handle_initialize(mcp_request)

        else:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {mcp_request.method}",
                    },
                    "id": mcp_request.id,
                },
            )

    @app.post("/mcp/stream")
    async def mcp_stream_endpoint(request: Request):
        """MCP endpoint with mandatory SSE streaming for tool calls.

        Always returns SSE stream for real-time progress updates.

        Args:
            request: FastAPI request object.

        Returns:
            StreamingResponse with SSE events.
        """
        try:
            body = await request.json()
            mcp_request = MCPRequest(**body)
        except Exception as e:
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
            )

        if mcp_request.method != "tools/call":
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Only tools/call supported for streaming'})}\n\n"

            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
            )

        params = mcp_request.params
        if isinstance(params, dict):
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
        else:
            tool_name = params.name
            arguments = params.arguments

        if tool_name not in TOOL_REGISTRY:
            async def error_stream():
                yield f"data: {json.dumps({'type': 'error', 'message': f'Tool not found: {tool_name}'})}\n\n"

            return StreamingResponse(
                error_stream(),
                media_type="text/event-stream",
            )

        executor = TOOL_REGISTRY[tool_name]
        sse_handler = SSEHandler()
        session = sse_handler.create_session()

        return StreamingResponse(
            stream_tool_result(tool_name, arguments, executor, session),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )


async def handle_initialize(request: MCPRequest) -> JSONResponse:
    """Handle MCP initialize request.

    Args:
        request: MCP request object.

    Returns:
        JSON response with server capabilities.
    """
    providers = get_available_providers()
    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True},
                },
                "serverInfo": {
                    "name": "price-comparison-mcp",
                    "version": "1.1.0",
                    "searchProviders": providers,
                },
            },
            "id": request.id,
        }
    )


async def handle_tools_list(request: MCPRequest) -> JSONResponse:
    """Handle MCP tools/list request.

    Args:
        request: MCP request object.

    Returns:
        JSON response with list of tools.
    """
    tools = [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": tool.inputSchema,
        }
        for tool in TOOL_DEFINITIONS
    ]

    return JSONResponse(
        content={
            "jsonrpc": "2.0",
            "result": {"tools": tools},
            "id": request.id,
        }
    )


async def handle_tools_call(request: MCPRequest) -> StreamingResponse:
    """Handle MCP tools/call request with SSE streaming.

    Args:
        request: MCP request object.

    Returns:
        Streaming response with SSE events.
    """
    params = request.params
    if isinstance(params, dict):
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
    else:
        tool_name = params.name
        arguments = params.arguments

    if tool_name not in TOOL_REGISTRY:
        async def error_stream():
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32602,
                    "message": f"Unknown tool: {tool_name}",
                },
                "id": request.id,
            }
            yield f"data: {json.dumps(error_response)}\n\n"

        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
        )

    async def tool_stream():
        executor = TOOL_REGISTRY[tool_name]

        # Start event
        yield f"data: {json.dumps({'type': 'start', 'tool': tool_name})}\n\n"

        try:
            # Execute tool
            result = await executor(**arguments)

            # Success response
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result)}],
                },
                "id": request.id,
            }
            yield f"data: {json.dumps({'type': 'result', 'data': response})}\n\n"

        except Exception as e:
            logger.error(f"Tool execution error: {tool_name} - {e}")
            error_response = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000,
                    "message": str(e),
                },
                "id": request.id,
            }
            yield f"data: {json.dumps({'type': 'error', 'data': error_response})}\n\n"

        # Complete event
        yield f"data: {json.dumps({'type': 'complete'})}\n\n"

    return StreamingResponse(
        tool_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# Create default app instance
app = create_app()
