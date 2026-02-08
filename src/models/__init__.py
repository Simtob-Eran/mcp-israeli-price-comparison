"""Data models and schemas for the unified MCP server."""

from .schemas import (
    ExtractedPrice,
    MCPRequest,
    MCPResponse,
    NormalizedProduct,
    PageContent,
    ParsedPrice,
    PriceHistory,
    PriceStatistics,
    ProductSpecs,
    SavedSearchResult,
    SearchResult,
    ShoppingResult,
    SSEEvent,
    StructuredData,
    TotalCost,
)

__all__ = [
    "ExtractedPrice",
    "MCPRequest",
    "MCPResponse",
    "NormalizedProduct",
    "PageContent",
    "ParsedPrice",
    "PriceHistory",
    "PriceStatistics",
    "ProductSpecs",
    "SavedSearchResult",
    "SearchResult",
    "ShoppingResult",
    "SSEEvent",
    "StructuredData",
    "TotalCost",
]
