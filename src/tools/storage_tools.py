"""Storage tools for persisting and retrieving price data from SQLite."""

import logging
from typing import Any, Dict, List, Optional

from ..utils.database import get_database
from ..utils.normalizer import TextNormalizer

logger = logging.getLogger(__name__)


async def save_search_result(
    product_name: str,
    url: str,
    price: float,
    currency: str,
    shipping_cost: Optional[float] = None,
    availability: Optional[str] = None,
    store_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Save price search result to SQLite database.

    Stores a price finding with automatic product name normalization
    for better matching in future queries.

    Args:
        product_name: Original product name as found.
        url: URL where the price was found.
        price: Price value.
        currency: Currency code (e.g., "ILS", "USD").
        shipping_cost: Optional shipping cost.
        availability: Optional availability status
            (e.g., "in_stock", "out_of_stock", "preorder").
        store_name: Optional name of the store/retailer.
        metadata: Optional additional metadata dictionary
            (e.g., {"condition": "new", "seller_rating": 4.5}).

    Returns:
        Dictionary containing:
        - id: Database record ID
        - success: Whether save was successful
        - normalized_name: The normalized product name used for matching
        - message: Status message

    Example:
        >>> result = await save_search_result(
        ...     product_name="Apple iPhone 15 Pro 256GB",
        ...     url="https://example.com/iphone15",
        ...     price=4999.00,
        ...     currency="ILS",
        ...     store_name="Example Store",
        ...     metadata={"color": "Black Titanium"}
        ... )
        >>> print(f"Saved with ID: {result['id']}")
    """
    try:
        # Normalize product name for better matching
        normalizer = TextNormalizer()
        normalized = normalizer.normalize(product_name)

        # Get database and save
        db = await get_database()
        record_id = await db.save_search_result(
            product_name=product_name,
            normalized_name=normalized.normalized,
            url=url,
            price=price,
            currency=currency,
            shipping_cost=shipping_cost,
            availability=availability,
            store_name=store_name,
            metadata=metadata,
        )

        return {
            "id": record_id,
            "success": True,
            "normalized_name": normalized.normalized,
            "message": "Search result saved successfully",
        }

    except Exception as e:
        logger.error(f"Failed to save search result: {e}")
        return {
            "id": None,
            "success": False,
            "normalized_name": None,
            "message": f"Failed to save: {str(e)}",
        }


async def get_price_history(
    product_name: str,
    days: int = 30,
    limit: int = 100,
) -> Dict[str, Any]:
    """Retrieve historical price data for a product.

    Searches for price records matching the product name (using normalized
    matching) within the specified time period.

    Args:
        product_name: Product name to search for (will be normalized).
        days: Number of days to look back. Default: 30.
        limit: Maximum number of results to return. Default: 100.

    Returns:
        Dictionary containing:
        - product_name: The queried product name
        - normalized_query: Normalized version used for matching
        - items: List of price history entries, each with:
            - id: Record ID
            - url: Source URL
            - price: Price value
            - currency: Currency code
            - date: Timestamp of record
            - store_name: Store name (if available)
            - metadata: Additional metadata
        - total_count: Total number of items returned
        - period_days: Number of days queried

    Example:
        >>> history = await get_price_history("iPhone 15 Pro", days=7)
        >>> for item in history["items"]:
        ...     print(f"{item['date']}: {item['price']} {item['currency']} at {item['store_name']}")
    """
    try:
        # Normalize product name for search
        normalizer = TextNormalizer()
        normalized = normalizer.normalize(product_name)

        # Get database and query
        db = await get_database()
        items = await db.get_price_history(
            product_name=normalized.normalized,
            days=days,
            limit=limit,
        )

        return {
            "product_name": product_name,
            "normalized_query": normalized.normalized,
            "items": items,
            "total_count": len(items),
            "period_days": days,
        }

    except Exception as e:
        logger.error(f"Failed to get price history: {e}")
        return {
            "product_name": product_name,
            "normalized_query": None,
            "items": [],
            "total_count": 0,
            "period_days": days,
            "error": str(e),
        }


async def get_average_market_price(
    product_name: str,
    days: int = 7,
) -> Dict[str, Any]:
    """Calculate average market price for recent searches.

    Computes statistics on prices found for a product within
    the specified time period, filtering outliers.

    Args:
        product_name: Product name to analyze (will be normalized).
        days: Number of days to include in analysis. Default: 7.

    Returns:
        Dictionary containing:
        - product_name: The queried product name
        - average: Average price
        - median: Median price
        - min: Minimum price found
        - max: Maximum price found
        - sample_size: Number of price points used
        - currency: Currency of the prices
        - period_days: Number of days analyzed

    Example:
        >>> stats = await get_average_market_price("Samsung Galaxy S24")
        >>> print(f"Average: {stats['average']} {stats['currency']}")
        >>> print(f"Range: {stats['min']} - {stats['max']}")
        >>> print(f"Based on {stats['sample_size']} prices")
    """
    try:
        # Normalize product name
        normalizer = TextNormalizer()
        normalized = normalizer.normalize(product_name)

        # Get database and calculate statistics
        db = await get_database()
        stats = await db.get_price_statistics(
            product_name=normalized.normalized,
            days=days,
        )

        if stats is None:
            return {
                "product_name": product_name,
                "average": 0,
                "median": 0,
                "min": 0,
                "max": 0,
                "sample_size": 0,
                "currency": "ILS",
                "period_days": days,
                "message": "No price data found for this product",
            }

        return {
            "product_name": product_name,
            "average": stats["average"],
            "median": stats["median"],
            "min": stats["min"],
            "max": stats["max"],
            "sample_size": stats["sample_size"],
            "currency": stats["currency"],
            "period_days": days,
        }

    except Exception as e:
        logger.error(f"Failed to get average market price: {e}")
        return {
            "product_name": product_name,
            "average": 0,
            "median": 0,
            "min": 0,
            "max": 0,
            "sample_size": 0,
            "currency": "ILS",
            "period_days": days,
            "error": str(e),
        }


async def delete_old_records(
    days: int = 90,
) -> Dict[str, Any]:
    """Delete search results older than specified days.

    Maintenance function to clean up old price data and keep
    the database size manageable.

    Args:
        days: Delete records older than this many days. Default: 90.

    Returns:
        Dictionary containing:
        - deleted_count: Number of records deleted
        - success: Whether operation was successful
        - message: Status message
    """
    try:
        db = await get_database()

        async with db.connection() as conn:
            from datetime import datetime, timedelta

            cutoff = datetime.now() - timedelta(days=days)

            cursor = await conn.execute(
                """
                DELETE FROM search_results
                WHERE created_at < ?
                """,
                (cutoff.isoformat(),),
            )
            await conn.commit()

            deleted_count = cursor.rowcount

        return {
            "deleted_count": deleted_count,
            "success": True,
            "message": f"Deleted {deleted_count} records older than {days} days",
        }

    except Exception as e:
        logger.error(f"Failed to delete old records: {e}")
        return {
            "deleted_count": 0,
            "success": False,
            "message": f"Failed to delete: {str(e)}",
        }


async def get_price_alerts(
    product_name: Optional[str] = None,
    active_only: bool = True,
) -> Dict[str, Any]:
    """Get configured price alerts.

    Retrieves price alerts that have been set up, optionally
    filtered by product name and active status.

    Args:
        product_name: Filter by product name (optional).
        active_only: Only return active alerts. Default: True.

    Returns:
        Dictionary containing:
        - alerts: List of alert configurations
        - total_count: Number of alerts returned
    """
    try:
        db = await get_database()

        async with db.connection() as conn:
            query = "SELECT * FROM price_alerts WHERE 1=1"
            params = []

            if active_only:
                query += " AND is_active = 1"

            if product_name:
                normalizer = TextNormalizer()
                normalized = normalizer.normalize(product_name)
                query += " AND normalized_name LIKE ?"
                params.append(f"%{normalized.normalized}%")

            query += " ORDER BY created_at DESC"

            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

            alerts = [
                {
                    "id": row["id"],
                    "product_name": row["product_name"],
                    "target_price": row["target_price"],
                    "currency": row["currency"],
                    "is_active": bool(row["is_active"]),
                    "created_at": row["created_at"],
                    "triggered_at": row["triggered_at"],
                }
                for row in rows
            ]

        return {
            "alerts": alerts,
            "total_count": len(alerts),
        }

    except Exception as e:
        logger.error(f"Failed to get price alerts: {e}")
        return {
            "alerts": [],
            "total_count": 0,
            "error": str(e),
        }


async def set_price_alert(
    product_name: str,
    target_price: float,
    currency: str = "ILS",
) -> Dict[str, Any]:
    """Set a price alert for a product.

    Creates an alert that can be checked when new prices are found.

    Args:
        product_name: Product to monitor.
        target_price: Target price threshold.
        currency: Currency for the target price. Default: "ILS".

    Returns:
        Dictionary containing:
        - id: Alert ID
        - success: Whether creation was successful
        - message: Status message
    """
    try:
        normalizer = TextNormalizer()
        normalized = normalizer.normalize(product_name)

        db = await get_database()

        async with db.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO price_alerts
                (product_name, normalized_name, target_price, currency)
                VALUES (?, ?, ?, ?)
                """,
                (product_name, normalized.normalized, target_price, currency),
            )
            await conn.commit()

            return {
                "id": cursor.lastrowid,
                "success": True,
                "message": f"Price alert set for {product_name} at {target_price} {currency}",
            }

    except Exception as e:
        logger.error(f"Failed to set price alert: {e}")
        return {
            "id": None,
            "success": False,
            "message": f"Failed to set alert: {str(e)}",
        }
