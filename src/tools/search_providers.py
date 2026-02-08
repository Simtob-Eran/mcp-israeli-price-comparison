"""Free search providers with fallback support."""

import json
import logging
import urllib.parse
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings

logger = logging.getLogger(__name__)


class SearchProvider(ABC):
    """Abstract base class for search providers."""

    name: str = "base"

    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform a web search."""
        pass

    @abstractmethod
    async def shopping_search(
        self,
        query: str,
        num_results: int = 20,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform a shopping search."""
        pass

    @abstractmethod
    async def image_search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform an image search."""
        pass


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo search provider - completely free, no API key required."""

    name = "duckduckgo"

    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://html.duckduckgo.com/html/"
        self.api_url = "https://api.duckduckgo.com/"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        region: str = "il-he",
        **kwargs,
    ) -> Dict[str, Any]:
        """Perform web search via DuckDuckGo HTML interface.

        Args:
            query: Search query.
            num_results: Number of results to return.
            region: Region code (e.g., 'il-he' for Israel Hebrew).

        Returns:
            Search results dictionary.
        """
        headers = {
            "User-Agent": self.settings.USER_AGENT,
        }

        params = {
            "q": query,
            "kl": region,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    data=params,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()

                results = self._parse_search_results(response.text, num_results)

                return {
                    "organic": results,
                    "knowledge_graph": None,
                    "related_searches": [],
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"DuckDuckGo search failed: {e}")
                raise

    def _parse_search_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse DuckDuckGo HTML search results."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        for i, result in enumerate(soup.select(".result")):
            if i >= limit:
                break

            title_elem = result.select_one(".result__title a")
            snippet_elem = result.select_one(".result__snippet")

            if title_elem:
                href = title_elem.get("href", "")
                actual_url = self._extract_url(href)

                results.append({
                    "title": title_elem.get_text(strip=True),
                    "link": actual_url,
                    "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    "position": i + 1,
                })

        return results

    def _extract_url(self, ddg_url: str) -> str:
        """Extract actual URL from DuckDuckGo redirect URL."""
        if "uddg=" in ddg_url:
            parsed = urllib.parse.urlparse(ddg_url)
            params = urllib.parse.parse_qs(parsed.query)
            if "uddg" in params:
                return urllib.parse.unquote(params["uddg"][0])
        return ddg_url

    async def shopping_search(
        self,
        query: str,
        num_results: int = 20,
        **kwargs,
    ) -> Dict[str, Any]:
        """DuckDuckGo doesn't have dedicated shopping - use regular search with price terms."""
        shopping_query = f"{query} price buy מחיר"

        search_results = await self.search(shopping_query, num_results)

        shopping_results = []
        for item in search_results.get("organic", []):
            shopping_results.append({
                "title": item.get("title", ""),
                "price": None,
                "link": item.get("link", ""),
                "source": self._extract_domain(item.get("link", "")),
                "rating": None,
                "reviews": None,
                "thumbnail": None,
            })

        return {
            "shopping_results": shopping_results,
            "search_parameters": {
                "query": query,
                "num_results": num_results,
                "provider": self.name,
            },
        }

    def _extract_domain(self, url: str) -> str:
        """Extract domain name from URL."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    async def image_search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """Search images via DuckDuckGo."""
        headers = {
            "User-Agent": self.settings.USER_AGENT,
        }

        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.api_url,
                    params=params,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                images = []

                if data.get("Image"):
                    images.append({
                        "title": data.get("Heading", query),
                        "image_url": data.get("Image"),
                        "link": data.get("AbstractURL", ""),
                        "source": data.get("AbstractSource", ""),
                        "thumbnail": data.get("Image"),
                    })

                for topic in data.get("RelatedTopics", [])[:num_results]:
                    if isinstance(topic, dict) and topic.get("Icon", {}).get("URL"):
                        images.append({
                            "title": topic.get("Text", "")[:100],
                            "image_url": topic["Icon"]["URL"],
                            "link": topic.get("FirstURL", ""),
                            "source": "DuckDuckGo",
                            "thumbnail": topic["Icon"]["URL"],
                        })

                return {
                    "images": images[:num_results],
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"DuckDuckGo image search failed: {e}")
                raise


class GoogleScraperProvider(SearchProvider):
    """Direct Google scraping - free but may be rate limited."""

    name = "google_scraper"

    def __init__(self):
        self.settings = get_settings()
        self.search_url = "https://www.google.com/search"
        self.shopping_url = "https://www.google.com/search"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        country: str = "il",
        language: str = "he",
        **kwargs,
    ) -> Dict[str, Any]:
        """Scrape Google search results directly."""
        headers = {
            "User-Agent": self.settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": f"{language},en;q=0.5",
        }

        params = {
            "q": query,
            "num": min(num_results + 5, 30),
            "hl": language,
            "gl": country,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.search_url,
                    params=params,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()

                results = self._parse_google_results(response.text, num_results)

                return {
                    "organic": results,
                    "knowledge_graph": None,
                    "related_searches": [],
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"Google scraper search failed: {e}")
                raise

    def _parse_google_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse Google search results HTML."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        selectors = [
            "div.g",
            "div[data-sokoban-container]",
            ".tF2Cxc",
        ]

        for selector in selectors:
            for result in soup.select(selector):
                if len(results) >= limit:
                    break

                link_elem = result.select_one("a[href^='http']")
                title_elem = result.select_one("h3")
                snippet_elem = result.select_one(".VwiC3b, .st, .s")

                if link_elem and title_elem:
                    href = link_elem.get("href", "")
                    if "google.com" not in href:
                        results.append({
                            "title": title_elem.get_text(strip=True),
                            "link": href,
                            "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                            "position": len(results) + 1,
                        })

            if results:
                break

        return results[:limit]

    async def shopping_search(
        self,
        query: str,
        num_results: int = 20,
        country: str = "il",
        language: str = "he",
        **kwargs,
    ) -> Dict[str, Any]:
        """Scrape Google Shopping results."""
        headers = {
            "User-Agent": self.settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": f"{language},en;q=0.5",
        }

        params = {
            "q": query,
            "tbm": "shop",
            "hl": language,
            "gl": country,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.shopping_url,
                    params=params,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()

                results = self._parse_shopping_results(response.text, num_results)

                return {
                    "shopping_results": results,
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"Google shopping scraper failed: {e}")
                raise

    def _parse_shopping_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse Google Shopping results HTML."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        for item in soup.select(".sh-dgr__content, .sh-dlr__list-result, [data-docid]"):
            if len(results) >= limit:
                break

            title_elem = item.select_one(".tAxDx, .Xjkr3b, h3, h4")
            price_elem = item.select_one(".a8Pemb, .HRLxBb, [data-price]")
            link_elem = item.select_one("a[href]")
            source_elem = item.select_one(".aULzUe, .IuHnof")
            img_elem = item.select_one("img")

            if title_elem:
                price_text = ""
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    if not price_text:
                        price_text = price_elem.get("data-price", "")

                results.append({
                    "title": title_elem.get_text(strip=True),
                    "price": price_text or None,
                    "link": link_elem.get("href", "") if link_elem else "",
                    "source": source_elem.get_text(strip=True) if source_elem else None,
                    "rating": None,
                    "reviews": None,
                    "thumbnail": img_elem.get("src") if img_elem else None,
                })

        return results

    async def image_search(
        self,
        query: str,
        num_results: int = 10,
        country: str = "il",
        language: str = "he",
        **kwargs,
    ) -> Dict[str, Any]:
        """Scrape Google Images results."""
        headers = {
            "User-Agent": self.settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": f"{language},en;q=0.5",
        }

        params = {
            "q": query,
            "tbm": "isch",
            "hl": language,
            "gl": country,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.search_url,
                    params=params,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()

                images = self._parse_image_results(response.text, num_results)

                return {
                    "images": images,
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"Google image scraper failed: {e}")
                raise

    def _parse_image_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse Google Images results."""
        soup = BeautifulSoup(html, "lxml")
        images = []

        for img in soup.select("img[data-src], img.rg_i"):
            if len(images) >= limit:
                break

            src = img.get("data-src") or img.get("src", "")
            if src and not src.startswith("data:"):
                parent = img.find_parent("a")
                link = parent.get("href", "") if parent else ""

                images.append({
                    "title": img.get("alt", ""),
                    "image_url": src,
                    "link": link,
                    "source": "",
                    "thumbnail": src,
                })

        return images


class BingScraperProvider(SearchProvider):
    """Bing search scraper - free alternative."""

    name = "bing_scraper"

    def __init__(self):
        self.settings = get_settings()
        self.search_url = "https://www.bing.com/search"

    async def search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """Scrape Bing search results."""
        headers = {
            "User-Agent": self.settings.USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        params = {
            "q": query,
            "count": num_results,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    self.search_url,
                    params=params,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()

                results = self._parse_bing_results(response.text, num_results)

                return {
                    "organic": results,
                    "knowledge_graph": None,
                    "related_searches": [],
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"Bing scraper search failed: {e}")
                raise

    def _parse_bing_results(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse Bing search results."""
        soup = BeautifulSoup(html, "lxml")
        results = []

        for i, result in enumerate(soup.select(".b_algo")):
            if i >= limit:
                break

            title_elem = result.select_one("h2 a")
            snippet_elem = result.select_one(".b_caption p")

            if title_elem:
                results.append({
                    "title": title_elem.get_text(strip=True),
                    "link": title_elem.get("href", ""),
                    "snippet": snippet_elem.get_text(strip=True) if snippet_elem else "",
                    "position": i + 1,
                })

        return results

    async def shopping_search(
        self,
        query: str,
        num_results: int = 20,
        **kwargs,
    ) -> Dict[str, Any]:
        """Bing shopping via regular search with price terms."""
        shopping_query = f"{query} buy price מחיר"
        search_results = await self.search(shopping_query, num_results)

        shopping_results = []
        for item in search_results.get("organic", []):
            shopping_results.append({
                "title": item.get("title", ""),
                "price": None,
                "link": item.get("link", ""),
                "source": self._extract_domain(item.get("link", "")),
                "rating": None,
                "reviews": None,
                "thumbnail": None,
            })

        return {
            "shopping_results": shopping_results,
            "search_parameters": {
                "query": query,
                "num_results": num_results,
                "provider": self.name,
            },
        }

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.netloc.replace("www.", "")
        except Exception:
            return ""

    async def image_search(
        self,
        query: str,
        num_results: int = 10,
        **kwargs,
    ) -> Dict[str, Any]:
        """Bing image search."""
        headers = {
            "User-Agent": self.settings.USER_AGENT,
        }

        params = {
            "q": query,
            "first": 1,
            "count": num_results,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    "https://www.bing.com/images/search",
                    params=params,
                    headers=headers,
                    timeout=30,
                    follow_redirects=True,
                )
                response.raise_for_status()

                images = self._parse_bing_images(response.text, num_results)

                return {
                    "images": images,
                    "search_parameters": {
                        "query": query,
                        "num_results": num_results,
                        "provider": self.name,
                    },
                }

            except Exception as e:
                logger.error(f"Bing image search failed: {e}")
                raise

    def _parse_bing_images(self, html: str, limit: int) -> List[Dict[str, Any]]:
        """Parse Bing image search results."""
        soup = BeautifulSoup(html, "lxml")
        images = []

        for item in soup.select(".iusc, .mimg"):
            if len(images) >= limit:
                break

            m_attr = item.get("m", "{}")
            try:
                metadata = json.loads(m_attr)
                images.append({
                    "title": metadata.get("t", ""),
                    "image_url": metadata.get("murl", ""),
                    "link": metadata.get("purl", ""),
                    "source": metadata.get("desc", ""),
                    "thumbnail": metadata.get("turl", ""),
                })
            except Exception:
                img = item.select_one("img")
                if img:
                    images.append({
                        "title": img.get("alt", ""),
                        "image_url": img.get("src", ""),
                        "link": "",
                        "source": "",
                        "thumbnail": img.get("src", ""),
                    })

        return images


# Provider registry - free providers only
PROVIDERS: Dict[str, SearchProvider] = {
    "duckduckgo": DuckDuckGoProvider(),
    "google_scraper": GoogleScraperProvider(),
    "bing_scraper": BingScraperProvider(),
}

# Default fallback order
DEFAULT_PROVIDER_ORDER = ["duckduckgo", "google_scraper", "bing_scraper"]


async def search_with_fallback(
    query: str,
    search_type: str = "search",
    num_results: int = 10,
    providers: Optional[List[str]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute search with automatic fallback to alternative providers.

    Args:
        query: Search query.
        search_type: Type of search ('search', 'shopping', 'images').
        num_results: Number of results.
        providers: List of providers to try in order. Default uses all providers.
        **kwargs: Additional search parameters.

    Returns:
        Search results from first successful provider.

    Raises:
        Exception: If all providers fail.
    """
    provider_order = providers or DEFAULT_PROVIDER_ORDER
    errors = []

    for provider_name in provider_order:
        provider = PROVIDERS.get(provider_name)
        if not provider:
            continue

        try:
            logger.info(f"Trying {provider_name} for {search_type}: {query}")

            if search_type == "search":
                result = await provider.search(query, num_results, **kwargs)
            elif search_type == "shopping":
                result = await provider.shopping_search(query, num_results, **kwargs)
            elif search_type == "images":
                result = await provider.image_search(query, num_results, **kwargs)
            else:
                raise ValueError(f"Unknown search type: {search_type}")

            # Verify we got results
            if search_type == "search" and result.get("organic"):
                logger.info(f"Success with {provider_name}")
                return result
            elif search_type == "shopping" and result.get("shopping_results"):
                logger.info(f"Success with {provider_name}")
                return result
            elif search_type == "images" and result.get("images"):
                logger.info(f"Success with {provider_name}")
                return result
            else:
                logger.warning(f"{provider_name} returned no results, trying next provider")
                continue

        except Exception as e:
            error_msg = f"{provider_name} failed: {str(e)}"
            logger.warning(error_msg)
            errors.append(error_msg)
            continue

    # All providers failed
    raise Exception(f"All search providers failed. Errors: {'; '.join(errors)}")
