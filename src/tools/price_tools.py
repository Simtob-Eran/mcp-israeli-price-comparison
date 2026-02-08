"""Price intelligence tools for parsing, normalizing, and analyzing price data."""

import logging
from typing import Any, Dict, List, Optional

from ..utils.normalizer import TextNormalizer
from ..utils.parser import PriceParser

logger = logging.getLogger(__name__)


async def parse_price(
    price_string: str,
    currency_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse price string to structured format.

    Handles various international price formats including:
    - Israeli Shekel: "₪1,234.56", "1234 ש״ח"
    - US Dollar: "$1,234.56", "1234 USD"
    - Euro: "1.234,56 €", "EUR 1234"
    - Multiple decimal/thousand separator conventions

    Args:
        price_string: The price string to parse (e.g., "₪1,234.56").
        currency_hint: Optional currency code if not detectable from string.

    Returns:
        Dictionary containing:
        - value: Parsed numeric value (float)
        - currency: Currency code (e.g., "ILS", "USD")
        - original: Original input string
        - locale: Detected locale/format (e.g., "us", "eu")

    Example:
        >>> result = await parse_price("₪1,234.56")
        >>> print(f"{result['value']} {result['currency']}")
        1234.56 ILS

        >>> result = await parse_price("1.234,56 €")
        >>> print(f"{result['value']} {result['currency']}")
        1234.56 EUR
    """
    parser = PriceParser()
    parsed = parser.parse(price_string, currency_hint)

    if parsed is None:
        return {
            "value": 0.0,
            "currency": currency_hint or "ILS",
            "original": price_string,
            "locale": None,
            "error": "Failed to parse price string",
        }

    return {
        "value": parsed.value,
        "currency": parsed.currency,
        "original": parsed.original,
        "locale": parsed.locale,
    }


async def normalize_product_name(
    product_name: str,
    remove_stopwords: bool = True,
) -> Dict[str, Any]:
    """Normalize product name for comparison and matching.

    Performs various normalization operations:
    - Removes common stopwords in English and Hebrew
    - Standardizes spacing and case
    - Removes special characters
    - Extracts brand name from known brands database
    - Extracts model number/name patterns
    - Detects product category hints

    Args:
        product_name: Original product name.
        remove_stopwords: Whether to remove common stopwords. Default: True.

    Returns:
        Dictionary containing:
        - normalized: Cleaned, normalized name
        - brand: Detected brand name (if any)
        - model: Detected model number/name (if any)
        - category_hints: List of detected category hints
        - original: Original input string

    Example:
        >>> result = await normalize_product_name("Apple iPhone 15 Pro Max 256GB Blue")
        >>> print(result)
        {
            "normalized": "apple iphone 15 pro max 256gb blue",
            "brand": "Apple",
            "model": "15 Pro Max",
            "category_hints": ["smartphone"],
            "original": "Apple iPhone 15 Pro Max 256GB Blue"
        }
    """
    normalizer = TextNormalizer(remove_stopwords=remove_stopwords)
    result = normalizer.normalize(product_name)

    return {
        "normalized": result.normalized,
        "brand": result.brand,
        "model": result.model,
        "category_hints": result.category_hints,
        "original": result.original,
    }


async def detect_product_specs(
    text: str,
    spec_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract technical specifications from text.

    Detects and extracts common product specifications using pattern matching:
    - Memory: "8GB RAM", "16GB DDR5"
    - Storage: "256GB SSD", "1TB NVMe"
    - Display: "6.1 inch", "15.6 אינץ"
    - Processor: "i7-13700K", "M2 Pro", "Snapdragon 8 Gen 2"
    - Color: "Space Gray", "Midnight Blue", "שחור"
    - Size: "M", "Large", "42mm"

    Args:
        text: Text containing specifications.
        spec_types: Types of specs to extract. Options:
            - "memory": RAM specifications
            - "storage": Storage capacity
            - "display": Screen size
            - "processor": CPU/chip info
            - "color": Color variations
            - "size": Physical size/dimensions
            Default: all types.

    Returns:
        Dictionary containing:
        - memory: Detected memory spec (if any)
        - storage: Detected storage spec (if any)
        - display: Detected display spec (if any)
        - processor: Detected processor spec (if any)
        - color: Detected color (if any)
        - size: Detected size (if any)
        - raw_specs: List of all detected specifications

    Example:
        >>> specs = await detect_product_specs(
        ...     "MacBook Pro 14 inch M2 Pro 16GB 512GB Space Gray"
        ... )
        >>> print(specs)
        {
            "memory": "16GB",
            "storage": "512GB",
            "display": "14 inch",
            "processor": "M2 Pro",
            "color": "Space Gray",
            "raw_specs": ["memory: 16GB", "storage: 512GB", ...]
        }
    """
    normalizer = TextNormalizer()
    specs = normalizer.extract_specs(text)

    result = {
        "memory": specs.memory,
        "storage": specs.storage,
        "color": specs.color,
        "size": specs.size,
        "display": specs.display,
        "processor": specs.processor,
        "raw_specs": specs.raw_specs,
    }

    # Filter by requested spec types if provided
    if spec_types:
        filtered = {k: v for k, v in result.items() if k in spec_types or k == "raw_specs"}
        return filtered

    return result


async def calculate_total_cost(
    base_price: float,
    shipping_cost: float = 0.0,
    tax_rate: float = 0.0,
    currency: str = "ILS",
    discount_percent: float = 0.0,
    additional_fees: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Calculate total cost including all fees and taxes.

    Computes the total purchase cost including:
    - Base product price
    - Shipping/delivery cost
    - Tax (calculated on base price)
    - Optional discounts
    - Additional fees (customs, handling, etc.)

    Args:
        base_price: Base product price.
        shipping_cost: Shipping/delivery cost. Default: 0.
        tax_rate: Tax rate as decimal (e.g., 0.17 for 17% VAT). Default: 0.
        currency: Currency code for the result. Default: "ILS".
        discount_percent: Discount percentage (0-100). Default: 0.
        additional_fees: Optional dictionary of additional fees
            (e.g., {"customs": 50, "handling": 10}).

    Returns:
        Dictionary containing:
        - base_price: Original base price
        - discount: Discount amount
        - discounted_price: Price after discount
        - shipping: Shipping cost
        - tax: Calculated tax amount
        - additional_fees: Sum of additional fees
        - total: Final total cost
        - currency: Currency code
        - breakdown: Detailed breakdown of all components

    Example:
        >>> cost = await calculate_total_cost(
        ...     base_price=1000,
        ...     shipping_cost=50,
        ...     tax_rate=0.17,
        ...     discount_percent=10,
        ...     additional_fees={"handling": 20}
        ... )
        >>> print(f"Total: {cost['total']} {cost['currency']}")
        Total: 1073.0 ILS

        >>> print(cost["breakdown"])
        {
            "base_price": 1000,
            "discount": -100,
            "discounted_price": 900,
            "shipping": 50,
            "tax": 153,
            "handling": 20,
            "total": 1073
        }
    """
    # Calculate discount
    discount_rate = min(100, max(0, discount_percent)) / 100
    discount_amount = round(base_price * discount_rate, 2)
    discounted_price = base_price - discount_amount

    # Calculate tax on discounted price
    tax = round(discounted_price * tax_rate, 2)

    # Sum additional fees
    fees = additional_fees or {}
    total_additional_fees = sum(fees.values())

    # Calculate total
    total = discounted_price + shipping_cost + tax + total_additional_fees

    # Build breakdown
    breakdown = {
        "base_price": base_price,
    }

    if discount_amount > 0:
        breakdown["discount"] = -discount_amount
        breakdown["discounted_price"] = discounted_price

    breakdown["shipping"] = shipping_cost

    if tax > 0:
        breakdown["tax"] = tax

    for fee_name, fee_amount in fees.items():
        breakdown[fee_name] = fee_amount

    breakdown["total"] = round(total, 2)

    return {
        "base_price": base_price,
        "discount": discount_amount,
        "discounted_price": discounted_price,
        "shipping": shipping_cost,
        "tax": tax,
        "additional_fees": total_additional_fees,
        "total": round(total, 2),
        "currency": currency,
        "breakdown": breakdown,
    }


async def compare_prices(
    prices: List[Dict[str, Any]],
    normalize_currency: bool = True,
    target_currency: str = "ILS",
) -> Dict[str, Any]:
    """Compare multiple prices and find the best deal.

    Analyzes a list of prices and returns comparison statistics
    including best price, average, and savings potential.

    Args:
        prices: List of price dictionaries with at least:
            - value: Numeric price
            - currency: Currency code
            Optional fields: source, url, shipping
        normalize_currency: Convert all prices to target currency. Default: True.
        target_currency: Currency for normalization. Default: "ILS".

    Returns:
        Dictionary containing:
        - best_price: Lowest price entry
        - worst_price: Highest price entry
        - average: Average price
        - median: Median price
        - price_range: Min/max range
        - potential_savings: Difference between highest and lowest
        - all_prices: Sorted list of all prices

    Example:
        >>> prices = [
        ...     {"value": 1000, "currency": "ILS", "source": "Store A"},
        ...     {"value": 950, "currency": "ILS", "source": "Store B"},
        ...     {"value": 1100, "currency": "ILS", "source": "Store C"},
        ... ]
        >>> comparison = await compare_prices(prices)
        >>> print(f"Best: {comparison['best_price']['value']} at {comparison['best_price']['source']}")
        Best: 950 at Store B
    """
    if not prices:
        return {
            "best_price": None,
            "worst_price": None,
            "average": 0,
            "median": 0,
            "price_range": {"min": 0, "max": 0},
            "potential_savings": 0,
            "all_prices": [],
        }

    parser = PriceParser()

    # Normalize currencies if requested
    normalized_prices = []
    for p in prices:
        value = p.get("value", 0)
        currency = p.get("currency", "ILS")

        if normalize_currency and currency != target_currency:
            value = parser.normalize_to_ils(value, currency)
            currency = target_currency

        normalized_prices.append({**p, "value": value, "currency": currency})

    # Sort by value
    sorted_prices = sorted(normalized_prices, key=lambda x: x.get("value", 0))
    values = [p.get("value", 0) for p in sorted_prices]

    # Calculate statistics
    avg = sum(values) / len(values)
    median_idx = len(values) // 2
    median = values[median_idx] if len(values) % 2 == 1 else (values[median_idx - 1] + values[median_idx]) / 2

    return {
        "best_price": sorted_prices[0],
        "worst_price": sorted_prices[-1],
        "average": round(avg, 2),
        "median": round(median, 2),
        "price_range": {"min": values[0], "max": values[-1]},
        "potential_savings": round(values[-1] - values[0], 2),
        "all_prices": sorted_prices,
        "currency": target_currency,
    }
