"""MCP tools for the unified price comparison server."""

from .price_tools import (
    calculate_total_cost,
    compare_prices,
    detect_product_specs,
    normalize_product_name,
    parse_price,
)
from .scraping_tools import (
    extract_prices_from_html,
    extract_structured_data,
    fetch_page_content,
)
from .serper_tools import (
    get_available_providers,
    image_search,
    serper_images,
    serper_search,
    serper_shopping,
    shopping_search,
    web_search,
)
from .storage_tools import (
    get_average_market_price,
    get_price_history,
    save_search_result,
)

__all__ = [
    # Search tools (with fallback support)
    "web_search",
    "shopping_search",
    "image_search",
    "get_available_providers",
    # Legacy aliases (backwards compatible)
    "serper_search",
    "serper_shopping",
    "serper_images",
    # Scraping tools
    "fetch_page_content",
    "extract_structured_data",
    "extract_prices_from_html",
    # Price tools
    "parse_price",
    "normalize_product_name",
    "detect_product_specs",
    "calculate_total_cost",
    "compare_prices",
    # Storage tools
    "save_search_result",
    "get_price_history",
    "get_average_market_price",
]
