"""Database utilities for SQLite operations."""

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

import aiosqlite

from ..config import get_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Async SQLite database manager."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file. Uses settings default if not provided.
        """
        settings = get_settings()
        self.db_path = db_path or settings.DATABASE_PATH
        self._ensure_db_directory()

    def _ensure_db_directory(self) -> None:
        """Ensure the database directory exists."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get an async database connection.

        Yields:
            aiosqlite.Connection: Database connection.
        """
        conn = await aiosqlite.connect(self.db_path)
        conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn.close()

    async def initialize(self) -> None:
        """Initialize database with schema from init.sql."""
        init_sql_path = Path(__file__).parent.parent.parent / "database" / "init.sql"

        if not init_sql_path.exists():
            logger.warning(f"init.sql not found at {init_sql_path}")
            return

        async with self.connection() as conn:
            with open(init_sql_path, "r") as f:
                sql_script = f.read()

            await conn.executescript(sql_script)
            await conn.commit()
            logger.info("Database initialized successfully")

    async def save_search_result(
        self,
        product_name: str,
        normalized_name: str,
        url: str,
        price: float,
        currency: str,
        shipping_cost: Optional[float] = None,
        availability: Optional[str] = None,
        store_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Save a price search result.

        Args:
            product_name: Original product name.
            normalized_name: Normalized product name for matching.
            url: URL where price was found.
            price: Price value.
            currency: Currency code.
            shipping_cost: Optional shipping cost.
            availability: Optional availability status.
            store_name: Optional store name.
            metadata: Optional additional metadata.

        Returns:
            int: ID of the inserted record.
        """
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO search_results
                (product_name, normalized_name, url, price, currency,
                 shipping_cost, availability, store_name, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product_name,
                    normalized_name,
                    url,
                    price,
                    currency,
                    shipping_cost,
                    availability,
                    store_name,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_price_history(
        self,
        product_name: str,
        days: int = 30,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get price history for a product.

        Args:
            product_name: Normalized product name to search for.
            days: Number of days to look back.
            limit: Maximum number of results.

        Returns:
            List of price history records.
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, url, price, currency, created_at, store_name, metadata
                FROM search_results
                WHERE normalized_name LIKE ?
                AND created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (f"%{product_name.lower()}%", cutoff_date.isoformat(), limit),
            )
            rows = await cursor.fetchall()

            return [
                {
                    "id": row["id"],
                    "url": row["url"],
                    "price": row["price"],
                    "currency": row["currency"],
                    "date": row["created_at"],
                    "store_name": row["store_name"],
                    "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
                }
                for row in rows
            ]

    async def get_price_statistics(
        self,
        product_name: str,
        days: int = 7,
    ) -> Optional[Dict[str, Any]]:
        """Calculate price statistics for a product.

        Args:
            product_name: Normalized product name.
            days: Number of days to include.

        Returns:
            Dictionary with price statistics or None if no data.
        """
        cutoff_date = datetime.now() - timedelta(days=days)

        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    AVG(price) as avg_price,
                    MIN(price) as min_price,
                    MAX(price) as max_price,
                    COUNT(*) as sample_size,
                    currency
                FROM search_results
                WHERE normalized_name LIKE ?
                AND created_at >= ?
                GROUP BY currency
                ORDER BY sample_size DESC
                LIMIT 1
                """,
                (f"%{product_name.lower()}%", cutoff_date.isoformat()),
            )
            row = await cursor.fetchone()

            if not row or row["sample_size"] == 0:
                return None

            # Calculate median
            cursor = await conn.execute(
                """
                SELECT price
                FROM search_results
                WHERE normalized_name LIKE ?
                AND created_at >= ?
                AND currency = ?
                ORDER BY price
                """,
                (f"%{product_name.lower()}%", cutoff_date.isoformat(), row["currency"]),
            )
            prices = [r["price"] for r in await cursor.fetchall()]
            median_price = prices[len(prices) // 2] if prices else 0

            return {
                "average": round(row["avg_price"], 2),
                "median": round(median_price, 2),
                "min": row["min_price"],
                "max": row["max_price"],
                "sample_size": row["sample_size"],
                "currency": row["currency"],
            }

    async def cache_response(
        self,
        query_hash: str,
        query_type: str,
        response: Dict[str, Any],
        ttl_minutes: int = 30,
    ) -> None:
        """Cache an API response.

        Args:
            query_hash: Hash of the query for lookup.
            query_type: Type of query (search, shopping, etc.).
            response: Response data to cache.
            ttl_minutes: Time-to-live in minutes.
        """
        expires_at = datetime.now() + timedelta(minutes=ttl_minutes)

        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO search_cache
                (query_hash, query_type, response, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (query_hash, query_type, json.dumps(response), expires_at.isoformat()),
            )
            await conn.commit()

    async def get_cached_response(
        self,
        query_hash: str,
    ) -> Optional[Dict[str, Any]]:
        """Get a cached response if not expired.

        Args:
            query_hash: Hash of the query.

        Returns:
            Cached response or None if not found/expired.
        """
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT response
                FROM search_cache
                WHERE query_hash = ?
                AND expires_at > ?
                """,
                (query_hash, datetime.now().isoformat()),
            )
            row = await cursor.fetchone()

            if row:
                return json.loads(row["response"])
            return None

    async def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries.

        Returns:
            Number of deleted entries.
        """
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                DELETE FROM search_cache
                WHERE expires_at <= ?
                """,
                (datetime.now().isoformat(),),
            )
            await conn.commit()
            return cursor.rowcount


# Global database instance
_db_instance: Optional[DatabaseManager] = None


async def get_database() -> DatabaseManager:
    """Get or create the global database manager instance.

    Returns:
        DatabaseManager: The database manager instance.
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseManager()
        await _db_instance.initialize()
    return _db_instance
