"""Serper API integration tools for web search functionality."""

import hashlib
import logging
from typing import Any, Dict, List, Optional

import httpx

from ..config import get_settings
from ..utils.database import get_database

logger = logging.getLogger(__name__)


class SerperAPIError(Exception):
    """Exception raised for Serper API errors."""

    pass


def _get_cache_key(query: str, search_type: str, **kwargs) -> str:
    """Generate cache key for a search query.

    Args:
        query: Search query.
        search_type: Type of search (search, shopping, images).
        **kwargs: Additional parameters.

    Returns:
        MD5 hash of the query parameters.
    """
    cache_str = f"{search_type}:{query}:{sorted(kwargs.items())}"
    return hashlib.md5(cache_str.encode()).hexdigest()


async def _make_serper_request(
    endpoint: str,
    payload: Dict[str, Any],
    timeout: int = 30,
) -> Dict[str, Any]:
    """Make a request to Serper API.

    Args:
        endpoint: API endpoint (search, shopping, images).
        payload: Request payload.
        timeout: Request timeout in seconds.

    Returns:
        API response data.

    Raises:
        SerperAPIError: If API request fails.
    """
    settings = get_settings()

    if not settings.SERPER_API_KEY:
        raise SerperAPIError("SERPER_API_KEY not configured")

    url = f"{settings.SERPER_BASE_URL}/{endpoint}"
    headers = {
        "X-API-KEY": settings.SERPER_API_KEY,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Serper API error: {e.response.status_code} - {e.response.text}")
            raise SerperAPIError(f"API returned {e.response.status_code}: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Serper request failed: {e}")
            raise SerperAPIError(f"Request failed: {str(e)}")


async def serper_search(
    query: str,
    num_results: int = 10,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Perform Google search via Serper API.

    Args:
        query: Search query string.
        num_results: Number of results to return (1-100).
        country: Country code for localized results (default: Israel).
        language: Language code for results (default: Hebrew).
        use_cache: Whether to use cached results if available.

    Returns:
        Dictionary containing:
        - organic: List of organic search results
        - knowledge_graph: Knowledge graph data if available
        - related_searches: List of related search queries
        - search_parameters: Parameters used for the search

    Example:
        >>> result = await serper_search("iPhone 15 Pro מחיר")
        >>> for item in result["organic"]:
        ...     print(f"{item['title']}: {item['link']}")
    """
    # Validate parameters
    num_results = max(1, min(100, num_results))

    # Check cache
    if use_cache:
        cache_key = _get_cache_key(query, "search", num=num_results, gl=country)
        db = await get_database()
        cached = await db.get_cached_response(cache_key)
        if cached:
            logger.info(f"Cache hit for search: {query}")
            return cached

    payload = {
        "q": query,
        "num": num_results,
        "gl": country,
        "hl": language,
    }

    response = await _make_serper_request("search", payload)

    # Structure the response
    result = {
        "organic": response.get("organic", []),
        "knowledge_graph": response.get("knowledgeGraph"),
        "related_searches": [
            item.get("query", "") for item in response.get("relatedSearches", [])
        ],
        "search_parameters": {
            "query": query,
            "num_results": num_results,
            "country": country,
            "language": language,
        },
    }

    # Cache the response
    if use_cache:
        db = await get_database()
        await db.cache_response(cache_key, "search", result, ttl_minutes=30)

    return result


async def serper_shopping(
    query: str,
    num_results: int = 20,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Perform Google Shopping search via Serper API.

    Specialized for product searches with pricing data. Returns structured
    shopping results including prices, ratings, and merchant information.

    Args:
        query: Product search query string.
        num_results: Number of results to return (1-100).
        country: Country code for localized results (default: Israel).
        language: Language code for results (default: Hebrew).
        use_cache: Whether to use cached results if available.

    Returns:
        Dictionary containing:
        - shopping_results: List of shopping items with:
            - title: Product title
            - price: Price string (may include currency)
            - link: Product page URL
            - source: Merchant/store name
            - rating: Product rating (float)
            - reviews: Number of reviews
            - thumbnail: Product image URL
        - search_parameters: Parameters used for the search

    Example:
        >>> result = await serper_shopping("Samsung Galaxy S24")
        >>> for item in result["shopping_results"]:
        ...     print(f"{item['title']}: {item['price']} at {item['source']}")
    """
    # Validate parameters
    num_results = max(1, min(100, num_results))

    # Check cache
    if use_cache:
        cache_key = _get_cache_key(query, "shopping", num=num_results, gl=country)
        db = await get_database()
        cached = await db.get_cached_response(cache_key)
        if cached:
            logger.info(f"Cache hit for shopping: {query}")
            return cached

    payload = {
        "q": query,
        "num": num_results,
        "gl": country,
        "hl": language,
    }

    response = await _make_serper_request("shopping", payload)

    # Structure the shopping results
    shopping_items = []
    for item in response.get("shopping", []):
        shopping_items.append(
            {
                "title": item.get("title", ""),
                "price": item.get("price"),
                "link": item.get("link", ""),
                "source": item.get("source"),
                "rating": item.get("rating"),
                "reviews": item.get("ratingCount"),
                "thumbnail": item.get("imageUrl"),
            }
        )

    result = {
        "shopping_results": shopping_items,
        "search_parameters": {
            "query": query,
            "num_results": num_results,
            "country": country,
            "language": language,
        },
    }

    # Cache the response
    if use_cache:
        db = await get_database()
        await db.cache_response(cache_key, "shopping", result, ttl_minutes=30)

    return result


async def serper_images(
    query: str,
    num_results: int = 10,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Search Google Images via Serper API.

    Useful for visual product identification and finding product images.

    Args:
        query: Image search query string.
        num_results: Number of results to return (1-100).
        country: Country code for localized results (default: Israel).
        language: Language code for results (default: Hebrew).
        use_cache: Whether to use cached results if available.

    Returns:
        Dictionary containing:
        - images: List of image results with:
            - title: Image title/alt text
            - image_url: Direct URL to the image
            - link: Source page URL
            - source: Website name
            - thumbnail: Thumbnail image URL
        - search_parameters: Parameters used for the search

    Example:
        >>> result = await serper_images("iPhone 15 Pro Max")
        >>> for img in result["images"]:
        ...     print(f"{img['title']}: {img['image_url']}")
    """
    # Validate parameters
    num_results = max(1, min(100, num_results))

    # Check cache
    if use_cache:
        cache_key = _get_cache_key(query, "images", num=num_results, gl=country)
        db = await get_database()
        cached = await db.get_cached_response(cache_key)
        if cached:
            logger.info(f"Cache hit for images: {query}")
            return cached

    payload = {
        "q": query,
        "num": num_results,
        "gl": country,
        "hl": language,
    }

    response = await _make_serper_request("images", payload)

    # Structure the image results
    images = []
    for item in response.get("images", []):
        images.append(
            {
                "title": item.get("title", ""),
                "image_url": item.get("imageUrl", ""),
                "link": item.get("link", ""),
                "source": item.get("source"),
                "thumbnail": item.get("thumbnailUrl"),
            }
        )

    result = {
        "images": images,
        "search_parameters": {
            "query": query,
            "num_results": num_results,
            "country": country,
            "language": language,
        },
    }

    # Cache the response
    if use_cache:
        db = await get_database()
        await db.cache_response(cache_key, "images", result, ttl_minutes=60)

    return result
