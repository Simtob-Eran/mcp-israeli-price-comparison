"""Pydantic schemas for tool inputs, outputs, and API models."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl


# =============================================================================
# SSE Event Models
# =============================================================================


class SSEEvent(BaseModel):
    """Server-Sent Event model."""

    type: Literal["start", "progress", "result", "error", "complete"]
    tool: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None


# =============================================================================
# MCP Protocol Models
# =============================================================================


class MCPToolParams(BaseModel):
    """Parameters for MCP tool call."""

    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class MCPRequest(BaseModel):
    """JSON-RPC request for MCP protocol."""

    jsonrpc: str = "2.0"
    method: str
    params: Optional[Union[MCPToolParams, Dict[str, Any]]] = None
    id: Optional[Union[str, int]] = None


class MCPError(BaseModel):
    """MCP error response."""

    code: int
    message: str
    data: Optional[Any] = None


class MCPResponse(BaseModel):
    """JSON-RPC response for MCP protocol."""

    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[MCPError] = None
    id: Optional[Union[str, int]] = None


# =============================================================================
# Search Result Models (Serper)
# =============================================================================


class OrganicResult(BaseModel):
    """Organic search result from Serper."""

    title: str
    link: str
    snippet: Optional[str] = None
    position: Optional[int] = None


class KnowledgeGraph(BaseModel):
    """Knowledge graph data from search."""

    title: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None


class SearchResult(BaseModel):
    """Complete search result from Serper API."""

    organic: List[OrganicResult] = Field(default_factory=list)
    knowledge_graph: Optional[KnowledgeGraph] = None
    related_searches: List[str] = Field(default_factory=list)
    search_parameters: Optional[Dict[str, Any]] = None


class ShoppingItem(BaseModel):
    """Individual shopping result item."""

    title: str
    price: Optional[str] = None
    link: str
    source: Optional[str] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    thumbnail: Optional[str] = None


class ShoppingResult(BaseModel):
    """Shopping search results from Serper API."""

    shopping_results: List[ShoppingItem] = Field(default_factory=list)
    search_parameters: Optional[Dict[str, Any]] = None


class ImageResult(BaseModel):
    """Image search result."""

    title: str
    image_url: str
    link: str
    source: Optional[str] = None
    thumbnail: Optional[str] = None


class ImagesResult(BaseModel):
    """Image search results from Serper API."""

    images: List[ImageResult] = Field(default_factory=list)
    search_parameters: Optional[Dict[str, Any]] = None


# =============================================================================
# Web Scraping Models
# =============================================================================


class PageContent(BaseModel):
    """Fetched page content result."""

    html: str
    status_code: int
    final_url: str
    headers: Dict[str, str] = Field(default_factory=dict)
    content_type: Optional[str] = None
    encoding: Optional[str] = None


class JsonLdData(BaseModel):
    """JSON-LD structured data."""

    type: Optional[str] = Field(None, alias="@type")
    context: Optional[str] = Field(None, alias="@context")
    data: Dict[str, Any] = Field(default_factory=dict)


class OpenGraphData(BaseModel):
    """Open Graph meta data."""

    title: Optional[str] = None
    description: Optional[str] = None
    image: Optional[str] = None
    url: Optional[str] = None
    type: Optional[str] = None
    site_name: Optional[str] = None
    price_amount: Optional[str] = None
    price_currency: Optional[str] = None


class StructuredData(BaseModel):
    """Extracted structured data from HTML."""

    json_ld: List[Dict[str, Any]] = Field(default_factory=list)
    microdata: Dict[str, Any] = Field(default_factory=dict)
    opengraph: Dict[str, Any] = Field(default_factory=dict)
    meta_tags: Dict[str, str] = Field(default_factory=dict)


class ExtractedPrice(BaseModel):
    """Price extracted from HTML."""

    value: float
    currency: str
    formatted: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str


# =============================================================================
# Price Intelligence Models
# =============================================================================


class ParsedPrice(BaseModel):
    """Parsed price information."""

    value: float
    currency: str
    original: str
    locale: Optional[str] = None


class NormalizedProduct(BaseModel):
    """Normalized product name result."""

    normalized: str
    brand: Optional[str] = None
    model: Optional[str] = None
    category_hints: List[str] = Field(default_factory=list)
    original: str


class ProductSpecs(BaseModel):
    """Extracted product specifications."""

    memory: Optional[str] = None
    storage: Optional[str] = None
    color: Optional[str] = None
    size: Optional[str] = None
    display: Optional[str] = None
    processor: Optional[str] = None
    raw_specs: List[str] = Field(default_factory=list)


class TotalCost(BaseModel):
    """Total cost calculation result."""

    base_price: float
    shipping: float
    tax: float
    total: float
    currency: str
    breakdown: Dict[str, float] = Field(default_factory=dict)


# =============================================================================
# Storage Models
# =============================================================================


class SavedSearchResult(BaseModel):
    """Result of saving a search result."""

    id: int
    success: bool
    message: Optional[str] = None


class PriceHistoryItem(BaseModel):
    """Single price history entry."""

    id: int
    url: str
    price: float
    currency: str
    date: datetime
    store_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class PriceHistory(BaseModel):
    """Price history for a product."""

    product_name: str
    items: List[PriceHistoryItem] = Field(default_factory=list)
    total_count: int


class PriceStatistics(BaseModel):
    """Average market price statistics."""

    average: float
    median: float
    min: float
    max: float
    sample_size: int
    currency: str
    period_days: int


# =============================================================================
# Tool Definitions for MCP
# =============================================================================


class ToolDefinition(BaseModel):
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: Dict[str, Any]


class ToolsList(BaseModel):
    """List of available tools."""

    tools: List[ToolDefinition]
