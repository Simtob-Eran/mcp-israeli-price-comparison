"""Web search tools with automatic fallback to free providers.

Supports multiple search providers with smart fallback:
1. Serper API (if API key is configured)
2. DuckDuckGo (free, no API key required)
3. Google direct scraping (free, may be rate limited)
4. Bing direct scraping (free backup)
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

from ..config import get_settings
from ..utils.database import get_database
from .search_providers import search_with_fallback, PROVIDERS

logger = logging.getLogger(__name__)


class SearchError(Exception):
    """Exception raised for search errors."""
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


async def web_search(
    query: str,
    num_results: int = 10,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
    preferred_providers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Perform web search with automatic fallback to free providers.

    Tries multiple search providers in order until one succeeds:
    1. Serper API (if SERPER_API_KEY is set)
    2. DuckDuckGo (free, no API key)
    3. Google scraping (free, may be rate limited)
    4. Bing scraping (free backup)

    Args:
        query: Search query string.
        num_results: Number of results to return (1-100).
        country: Country code for localized results (default: Israel).
        language: Language code for results (default: Hebrew).
        use_cache: Whether to use cached results if available.
        preferred_providers: Optional list of providers to try in order.
            Options: 'serper', 'duckduckgo', 'google_scraper', 'bing_scraper'

    Returns:
        Dictionary containing:
        - organic: List of organic search results
        - knowledge_graph: Knowledge graph data if available
        - related_searches: List of related search queries
        - search_parameters: Parameters used for the search
        - provider: Which provider returned the results

    Example:
        >>> result = await web_search("iPhone 15 Pro מחיר")
        >>> print(f"Results from: {result['search_parameters']['provider']}")
        >>> for item in result["organic"]:
        ...     print(f"{item['title']}: {item['link']}")
    """
    # Validate parameters
    num_results = max(1, min(100, num_results))

    # Check cache
    if use_cache:
        cache_key = _get_cache_key(query, "search", num=num_results, gl=country)
        try:
            db = await get_database()
            cached = await db.get_cached_response(cache_key)
            if cached:
                logger.info(f"Cache hit for search: {query}")
                cached["from_cache"] = True
                return cached
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

    # Perform search with fallback
    try:
        result = await search_with_fallback(
            query=query,
            search_type="search",
            num_results=num_results,
            providers=preferred_providers,
            country=country,
            language=language,
        )

        # Cache the response
        if use_cache:
            try:
                db = await get_database()
                await db.cache_response(cache_key, "search", result, ttl_minutes=30)
            except Exception as e:
                logger.warning(f"Cache save failed: {e}")

        return result

    except Exception as e:
        logger.error(f"All search providers failed for query: {query}")
        raise SearchError(f"Search failed: {str(e)}")


async def shopping_search(
    query: str,
    num_results: int = 20,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
    preferred_providers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Perform shopping search with automatic fallback to free providers.

    Specialized for product searches with pricing data. Uses fallback:
    1. Serper Shopping API (if key available)
    2. Google Shopping scraping
    3. DuckDuckGo with price keywords
    4. Bing with price keywords

    Args:
        query: Product search query string.
        num_results: Number of results to return (1-100).
        country: Country code for localized results (default: Israel).
        language: Language code for results (default: Hebrew).
        use_cache: Whether to use cached results if available.
        preferred_providers: Optional list of providers to try.

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
        - provider: Which provider returned the results

    Example:
        >>> result = await shopping_search("Samsung Galaxy S24")
        >>> print(f"Provider: {result['search_parameters']['provider']}")
        >>> for item in result["shopping_results"]:
        ...     print(f"{item['title']}: {item['price']} at {item['source']}")
    """
    # Validate parameters
    num_results = max(1, min(100, num_results))

    # Check cache
    if use_cache:
        cache_key = _get_cache_key(query, "shopping", num=num_results, gl=country)
        try:
            db = await get_database()
            cached = await db.get_cached_response(cache_key)
            if cached:
                logger.info(f"Cache hit for shopping: {query}")
                cached["from_cache"] = True
                return cached
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

    # Perform shopping search with fallback
    try:
        result = await search_with_fallback(
            query=query,
            search_type="shopping",
            num_results=num_results,
            providers=preferred_providers,
            country=country,
            language=language,
        )

        # Cache the response
        if use_cache:
            try:
                db = await get_database()
                await db.cache_response(cache_key, "shopping", result, ttl_minutes=30)
            except Exception as e:
                logger.warning(f"Cache save failed: {e}")

        return result

    except Exception as e:
        logger.error(f"All shopping providers failed for query: {query}")
        raise SearchError(f"Shopping search failed: {str(e)}")


async def image_search(
    query: str,
    num_results: int = 10,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
    preferred_providers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Search images with automatic fallback to free providers.

    Useful for visual product identification. Uses fallback:
    1. Serper Images API (if key available)
    2. Google Images scraping
    3. Bing Images scraping
    4. DuckDuckGo instant answers

    Args:
        query: Image search query string.
        num_results: Number of results to return (1-100).
        country: Country code for localized results (default: Israel).
        language: Language code for results (default: Hebrew).
        use_cache: Whether to use cached results if available.
        preferred_providers: Optional list of providers to try.

    Returns:
        Dictionary containing:
        - images: List of image results with:
            - title: Image title/alt text
            - image_url: Direct URL to the image
            - link: Source page URL
            - source: Website name
            - thumbnail: Thumbnail image URL
        - search_parameters: Parameters used for the search
        - provider: Which provider returned the results

    Example:
        >>> result = await image_search("iPhone 15 Pro Max")
        >>> for img in result["images"]:
        ...     print(f"{img['title']}: {img['image_url']}")
    """
    # Validate parameters
    num_results = max(1, min(100, num_results))

    # Check cache
    if use_cache:
        cache_key = _get_cache_key(query, "images", num=num_results, gl=country)
        try:
            db = await get_database()
            cached = await db.get_cached_response(cache_key)
            if cached:
                logger.info(f"Cache hit for images: {query}")
                cached["from_cache"] = True
                return cached
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")

    # Perform image search with fallback
    try:
        result = await search_with_fallback(
            query=query,
            search_type="images",
            num_results=num_results,
            providers=preferred_providers,
            country=country,
            language=language,
        )

        # Cache the response
        if use_cache:
            try:
                db = await get_database()
                await db.cache_response(cache_key, "images", result, ttl_minutes=60)
            except Exception as e:
                logger.warning(f"Cache save failed: {e}")

        return result

    except Exception as e:
        logger.error(f"All image providers failed for query: {query}")
        raise SearchError(f"Image search failed: {str(e)}")


# Backwards compatibility aliases (old function names still work)
async def serper_search(
    query: str,
    num_results: int = 10,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Backwards compatible alias for web_search.

    Note: Now uses automatic fallback to free providers if Serper API key
    is not available.
    """
    return await web_search(
        query=query,
        num_results=num_results,
        country=country,
        language=language,
        use_cache=use_cache,
    )


async def serper_shopping(
    query: str,
    num_results: int = 20,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Backwards compatible alias for shopping_search.

    Note: Now uses automatic fallback to free providers if Serper API key
    is not available.
    """
    return await shopping_search(
        query=query,
        num_results=num_results,
        country=country,
        language=language,
        use_cache=use_cache,
    )


async def serper_images(
    query: str,
    num_results: int = 10,
    country: str = "il",
    language: str = "he",
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Backwards compatible alias for image_search.

    Note: Now uses automatic fallback to free providers if Serper API key
    is not available.
    """
    return await image_search(
        query=query,
        num_results=num_results,
        country=country,
        language=language,
        use_cache=use_cache,
    )


def get_available_providers() -> List[str]:
    """Get list of available search providers.

    Returns:
        List of provider names that are currently available.
    """
    settings = get_settings()
    available = []

    for name, provider in PROVIDERS.items():
        if name == "serper":
            if settings.SERPER_API_KEY:
                available.append(name)
        else:
            available.append(name)

    return available
