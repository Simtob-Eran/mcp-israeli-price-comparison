"""Web scraping tools for fetching and extracting data from web pages."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from ..config import get_settings
from ..utils.parser import PriceParser

logger = logging.getLogger(__name__)


class ScrapingError(Exception):
    """Exception raised for scraping errors."""

    pass


async def fetch_page_content(
    url: str,
    render_js: bool = False,
    timeout: int = 30,
    follow_redirects: bool = True,
) -> Dict[str, Any]:
    """Fetch HTML content of a web page.

    Supports both static page fetching with httpx and JavaScript rendering
    with Playwright for dynamic content.

    Args:
        url: Target URL to fetch.
        render_js: Use Playwright for JavaScript rendering (slower but handles SPAs).
        timeout: Request timeout in seconds.
        follow_redirects: Whether to follow HTTP redirects.

    Returns:
        Dictionary containing:
        - html: Raw HTML content
        - status_code: HTTP status code
        - final_url: Final URL after redirects
        - headers: Response headers
        - content_type: Content-Type header value
        - encoding: Response encoding

    Raises:
        ScrapingError: If page fetch fails.

    Example:
        >>> content = await fetch_page_content("https://example.com/product")
        >>> print(f"Status: {content['status_code']}")
        >>> print(f"HTML length: {len(content['html'])}")
    """
    settings = get_settings()

    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ScrapingError(f"Invalid URL: {url}")

    if render_js:
        return await _fetch_with_playwright(url, timeout)
    else:
        return await _fetch_with_httpx(url, timeout, follow_redirects)


async def _fetch_with_httpx(
    url: str,
    timeout: int,
    follow_redirects: bool,
) -> Dict[str, Any]:
    """Fetch page using httpx (static content).

    Args:
        url: Target URL.
        timeout: Request timeout.
        follow_redirects: Whether to follow redirects.

    Returns:
        Page content dictionary.
    """
    settings = get_settings()

    headers = {
        "User-Agent": settings.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,he;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
    }

    async with httpx.AsyncClient(follow_redirects=follow_redirects) as client:
        try:
            response = await client.get(url, headers=headers, timeout=timeout)

            return {
                "html": response.text,
                "status_code": response.status_code,
                "final_url": str(response.url),
                "headers": dict(response.headers),
                "content_type": response.headers.get("content-type"),
                "encoding": response.encoding,
            }
        except httpx.HTTPStatusError as e:
            raise ScrapingError(f"HTTP error {e.response.status_code}: {url}")
        except httpx.RequestError as e:
            raise ScrapingError(f"Request failed for {url}: {str(e)}")


async def _fetch_with_playwright(
    url: str,
    timeout: int,
) -> Dict[str, Any]:
    """Fetch page using Playwright (JavaScript rendered content).

    Args:
        url: Target URL.
        timeout: Request timeout in seconds.

    Returns:
        Page content dictionary.
    """
    settings = get_settings()

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ScrapingError("Playwright not installed. Run: pip install playwright && playwright install")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.PLAYWRIGHT_HEADLESS)

        try:
            context = await browser.new_context(
                user_agent=settings.USER_AGENT,
                viewport={"width": 1920, "height": 1080},
            )
            page = await context.new_page()

            response = await page.goto(url, timeout=timeout * 1000, wait_until="networkidle")

            html = await page.content()
            final_url = page.url

            return {
                "html": html,
                "status_code": response.status if response else 200,
                "final_url": final_url,
                "headers": dict(response.headers) if response else {},
                "content_type": response.headers.get("content-type") if response else None,
                "encoding": "utf-8",
            }
        finally:
            await browser.close()


async def extract_structured_data(
    html: str,
    data_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract structured data from HTML.

    Extracts various forms of structured data embedded in HTML including
    JSON-LD, Schema.org microdata, Open Graph tags, and standard meta tags.

    Args:
        html: HTML content to parse.
        data_types: Types of data to extract. Options:
            - "json-ld": JSON-LD scripts (Schema.org)
            - "microdata": HTML microdata attributes
            - "opengraph": Open Graph meta tags
            - "meta": Standard meta tags
            Default: all types.

    Returns:
        Dictionary containing:
        - json_ld: List of JSON-LD objects found
        - microdata: Extracted microdata attributes
        - opengraph: Open Graph tag values
        - meta_tags: Standard meta tag values

    Example:
        >>> data = await extract_structured_data(html)
        >>> if data["json_ld"]:
        ...     for item in data["json_ld"]:
        ...         if item.get("@type") == "Product":
        ...             print(f"Product: {item.get('name')}")
    """
    if data_types is None:
        data_types = ["json-ld", "microdata", "opengraph", "meta"]

    soup = BeautifulSoup(html, "lxml")
    result = {
        "json_ld": [],
        "microdata": {},
        "opengraph": {},
        "meta_tags": {},
    }

    # Extract JSON-LD
    if "json-ld" in data_types:
        result["json_ld"] = _extract_json_ld(soup)

    # Extract microdata
    if "microdata" in data_types:
        result["microdata"] = _extract_microdata(soup)

    # Extract Open Graph
    if "opengraph" in data_types:
        result["opengraph"] = _extract_opengraph(soup)

    # Extract meta tags
    if "meta" in data_types:
        result["meta_tags"] = _extract_meta_tags(soup)

    return result


def _extract_json_ld(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """Extract JSON-LD structured data.

    Args:
        soup: BeautifulSoup parsed HTML.

    Returns:
        List of JSON-LD objects.
    """
    json_ld_data = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            content = script.string
            if content:
                data = json.loads(content)
                if isinstance(data, list):
                    json_ld_data.extend(data)
                else:
                    json_ld_data.append(data)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON-LD: {e}")
            continue

    return json_ld_data


def _extract_microdata(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract Schema.org microdata.

    Args:
        soup: BeautifulSoup parsed HTML.

    Returns:
        Dictionary of microdata attributes.
    """
    microdata = {}

    # Find elements with itemtype (Schema.org)
    for item in soup.find_all(attrs={"itemtype": True}):
        item_type = item.get("itemtype", "")

        # Extract itemprops within this scope
        props = {}
        for prop in item.find_all(attrs={"itemprop": True}):
            prop_name = prop.get("itemprop")
            prop_value = (
                prop.get("content")
                or prop.get("href")
                or prop.get("src")
                or prop.get_text(strip=True)
            )
            if prop_name and prop_value:
                props[prop_name] = prop_value

        if props:
            # Use Schema.org type as key
            type_name = item_type.split("/")[-1] if "/" in item_type else item_type
            microdata[type_name] = props

    return microdata


def _extract_opengraph(soup: BeautifulSoup) -> Dict[str, Any]:
    """Extract Open Graph meta tags.

    Args:
        soup: BeautifulSoup parsed HTML.

    Returns:
        Dictionary of Open Graph values.
    """
    og_data = {}

    for meta in soup.find_all("meta", attrs={"property": True}):
        prop = meta.get("property", "")
        if prop.startswith("og:"):
            key = prop[3:]  # Remove "og:" prefix
            og_data[key] = meta.get("content", "")

    # Also check product-specific tags
    for meta in soup.find_all("meta", attrs={"property": True}):
        prop = meta.get("property", "")
        if prop.startswith("product:"):
            key = prop.replace(":", "_")
            og_data[key] = meta.get("content", "")

    return og_data


def _extract_meta_tags(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract standard meta tags.

    Args:
        soup: BeautifulSoup parsed HTML.

    Returns:
        Dictionary of meta tag values.
    """
    meta_tags = {}

    for meta in soup.find_all("meta"):
        name = meta.get("name") or meta.get("http-equiv")
        content = meta.get("content")

        if name and content:
            meta_tags[name.lower()] = content

    return meta_tags


async def extract_prices_from_html(
    html: str,
    currency_hints: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Extract all prices from HTML using multiple strategies.

    Uses multiple extraction methods to find prices:
    1. Schema.org Product structured data
    2. Common CSS selectors for price elements
    3. Open Graph price tags
    4. Regex patterns for currency symbols

    Args:
        html: HTML content to parse.
        currency_hints: Currency symbols/codes to look for.
            Default: ["₪", "ILS", "$", "USD"]

    Returns:
        List of extracted prices, each containing:
        - value: Numeric price value
        - currency: Currency code
        - formatted: Original formatted string
        - confidence: Confidence score (0-1)
        - source: How the price was found

    Example:
        >>> prices = await extract_prices_from_html(html)
        >>> best_price = max(prices, key=lambda p: p["confidence"])
        >>> print(f"Price: {best_price['value']} {best_price['currency']}")
    """
    if currency_hints is None:
        currency_hints = ["₪", "ILS", "$", "USD", "€", "EUR"]

    soup = BeautifulSoup(html, "lxml")
    parser = PriceParser()
    prices = []
    seen_values = set()

    # Strategy 1: Schema.org Product JSON-LD
    json_ld_prices = _extract_prices_from_json_ld(soup, parser)
    for price in json_ld_prices:
        if price["value"] not in seen_values:
            seen_values.add(price["value"])
            prices.append(price)

    # Strategy 2: Open Graph price tags
    og_prices = _extract_prices_from_opengraph(soup, parser)
    for price in og_prices:
        if price["value"] not in seen_values:
            seen_values.add(price["value"])
            prices.append(price)

    # Strategy 3: Common CSS selectors
    selector_prices = _extract_prices_from_selectors(soup, parser)
    for price in selector_prices:
        if price["value"] not in seen_values:
            seen_values.add(price["value"])
            prices.append(price)

    # Strategy 4: Regex patterns
    regex_prices = _extract_prices_from_regex(soup.get_text(), parser, currency_hints)
    for price in regex_prices:
        if price["value"] not in seen_values:
            seen_values.add(price["value"])
            prices.append(price)

    # Sort by confidence
    prices.sort(key=lambda x: x["confidence"], reverse=True)

    return prices


def _extract_prices_from_json_ld(
    soup: BeautifulSoup,
    parser: PriceParser,
) -> List[Dict[str, Any]]:
    """Extract prices from JSON-LD structured data.

    Args:
        soup: Parsed HTML.
        parser: Price parser instance.

    Returns:
        List of price dictionaries.
    """
    prices = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string) if script.string else None
            if not data:
                continue

            items = data if isinstance(data, list) else [data]

            for item in items:
                if item.get("@type") == "Product":
                    offers = item.get("offers", {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}

                    price = offers.get("price")
                    currency = offers.get("priceCurrency", "ILS")

                    if price:
                        try:
                            value = float(price)
                            prices.append(
                                {
                                    "value": value,
                                    "currency": currency,
                                    "formatted": f"{currency} {value}",
                                    "confidence": 0.95,
                                    "source": "json-ld",
                                }
                            )
                        except (ValueError, TypeError):
                            pass
        except json.JSONDecodeError:
            continue

    return prices


def _extract_prices_from_opengraph(
    soup: BeautifulSoup,
    parser: PriceParser,
) -> List[Dict[str, Any]]:
    """Extract prices from Open Graph tags.

    Args:
        soup: Parsed HTML.
        parser: Price parser instance.

    Returns:
        List of price dictionaries.
    """
    prices = []

    # Look for og:price:amount and og:price:currency
    price_meta = soup.find("meta", attrs={"property": "og:price:amount"})
    currency_meta = soup.find("meta", attrs={"property": "og:price:currency"})

    if price_meta:
        try:
            value = float(price_meta.get("content", "0"))
            currency = currency_meta.get("content", "ILS") if currency_meta else "ILS"
            prices.append(
                {
                    "value": value,
                    "currency": currency,
                    "formatted": f"{currency} {value}",
                    "confidence": 0.9,
                    "source": "opengraph",
                }
            )
        except (ValueError, TypeError):
            pass

    # Also check product:price:amount
    price_meta = soup.find("meta", attrs={"property": "product:price:amount"})
    currency_meta = soup.find("meta", attrs={"property": "product:price:currency"})

    if price_meta:
        try:
            value = float(price_meta.get("content", "0"))
            currency = currency_meta.get("content", "ILS") if currency_meta else "ILS"
            prices.append(
                {
                    "value": value,
                    "currency": currency,
                    "formatted": f"{currency} {value}",
                    "confidence": 0.9,
                    "source": "opengraph-product",
                }
            )
        except (ValueError, TypeError):
            pass

    return prices


def _extract_prices_from_selectors(
    soup: BeautifulSoup,
    parser: PriceParser,
) -> List[Dict[str, Any]]:
    """Extract prices using common CSS selectors.

    Args:
        soup: Parsed HTML.
        parser: Price parser instance.

    Returns:
        List of price dictionaries.
    """
    prices = []

    # Common price-related CSS selectors
    selectors = [
        "[class*='price']",
        "[class*='Price']",
        "[class*='cost']",
        "[class*='amount']",
        "[id*='price']",
        "[data-price]",
        "[itemprop='price']",
        ".product-price",
        ".sale-price",
        ".regular-price",
        ".current-price",
        ".final-price",
        "span.price",
        "div.price",
        ".price-box",
        ".price-wrapper",
    ]

    for selector in selectors:
        try:
            elements = soup.select(selector)
            for elem in elements[:5]:  # Limit to first 5 matches per selector
                text = elem.get_text(strip=True)

                # Also check for data-price attribute
                data_price = elem.get("data-price")
                if data_price:
                    try:
                        value = float(data_price)
                        prices.append(
                            {
                                "value": value,
                                "currency": "ILS",
                                "formatted": text or str(value),
                                "confidence": 0.8,
                                "source": f"selector:{selector}",
                            }
                        )
                        continue
                    except (ValueError, TypeError):
                        pass

                # Parse text content
                if text:
                    parsed = parser.parse(text)
                    if parsed and 0.01 < parsed.value < 1000000:
                        prices.append(
                            {
                                "value": parsed.value,
                                "currency": parsed.currency,
                                "formatted": text,
                                "confidence": 0.7,
                                "source": f"selector:{selector}",
                            }
                        )
        except Exception as e:
            logger.debug(f"Selector {selector} failed: {e}")
            continue

    return prices


def _extract_prices_from_regex(
    text: str,
    parser: PriceParser,
    currency_hints: List[str],
) -> List[Dict[str, Any]]:
    """Extract prices using regex patterns.

    Args:
        text: Text content to search.
        parser: Price parser instance.
        currency_hints: Currency symbols to look for.

    Returns:
        List of price dictionaries.
    """
    prices = []
    parsed_prices = parser.extract_all_prices(text, currency_hints)

    for parsed in parsed_prices:
        # Filter out unrealistic prices
        if 0.01 < parsed.value < 1000000:
            prices.append(
                {
                    "value": parsed.value,
                    "currency": parsed.currency,
                    "formatted": parsed.original,
                    "confidence": 0.5,
                    "source": "regex",
                }
            )

    return prices
