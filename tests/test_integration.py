"""Integration tests for the MCP server."""

import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from src.tools.price_tools import compare_prices
from src.tools.storage_tools import (
    get_average_market_price,
    get_price_history,
    save_search_result,
)
from src.utils.database import DatabaseManager


class TestDatabaseIntegration:
    """Integration tests for database operations."""

    @pytest_asyncio.fixture
    async def db(self):
        """Create temporary database for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(db_path=f"{tmpdir}/test.db")
            await db.initialize()
            yield db

    @pytest.mark.asyncio
    async def test_save_and_retrieve_price(self, db):
        """Test saving and retrieving a price record."""
        # Save a price
        record_id = await db.save_search_result(
            product_name="iPhone 15 Pro",
            normalized_name="iphone 15 pro",
            url="https://example.com/iphone",
            price=4999.00,
            currency="ILS",
            store_name="Test Store",
        )

        assert record_id > 0

        # Retrieve the price
        history = await db.get_price_history("iphone 15 pro", days=1)

        assert len(history) == 1
        assert history[0]["price"] == 4999.00

    @pytest.mark.asyncio
    async def test_price_statistics(self, db):
        """Test price statistics calculation."""
        # Save multiple prices
        prices = [4999.00, 4899.00, 5199.00, 4799.00, 5099.00]

        for i, price in enumerate(prices):
            await db.save_search_result(
                product_name="iPhone 15 Pro",
                normalized_name="iphone 15 pro",
                url=f"https://store{i}.com/iphone",
                price=price,
                currency="ILS",
                store_name=f"Store {i}",
            )

        # Get statistics
        stats = await db.get_price_statistics("iphone 15 pro", days=1)

        assert stats is not None
        assert stats["sample_size"] == 5
        assert stats["min"] == 4799.00
        assert stats["max"] == 5199.00
        assert 4900 < stats["average"] < 5000

    @pytest.mark.asyncio
    async def test_cache_operations(self, db):
        """Test cache save and retrieve."""
        test_data = {"results": [1, 2, 3]}

        # Cache response
        await db.cache_response(
            query_hash="test_hash",
            query_type="search",
            response=test_data,
            ttl_minutes=5,
        )

        # Retrieve from cache
        cached = await db.get_cached_response("test_hash")

        assert cached is not None
        assert cached["results"] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_expired_cache(self, db):
        """Test that expired cache returns None."""
        # Cache with 0 TTL (already expired)
        await db.cache_response(
            query_hash="expired_hash",
            query_type="search",
            response={"data": "test"},
            ttl_minutes=0,
        )

        # Should not retrieve expired cache
        cached = await db.get_cached_response("expired_hash")

        assert cached is None


class TestStorageToolsIntegration:
    """Integration tests for storage tools."""

    @pytest_asyncio.fixture
    async def setup_db(self, monkeypatch):
        """Setup temporary database for storage tools."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Monkeypatch the database path
            db_path = f"{tmpdir}/test.db"

            # Create and initialize db
            db = DatabaseManager(db_path=db_path)
            await db.initialize()

            # Monkeypatch get_database to return our test db
            async def mock_get_database():
                return db

            from src.utils import database

            monkeypatch.setattr(database, "get_database", mock_get_database)
            monkeypatch.setattr(database, "_db_instance", db)

            yield db

    @pytest.mark.asyncio
    async def test_save_search_result_tool(self, setup_db):
        """Test save_search_result tool."""
        result = await save_search_result(
            product_name="Test Product",
            url="https://example.com/product",
            price=100.00,
            currency="ILS",
            store_name="Test Store",
        )

        assert result["success"] is True
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_get_price_history_tool(self, setup_db):
        """Test get_price_history tool."""
        # First save some data
        await save_search_result(
            product_name="Test Product",
            url="https://example.com/product",
            price=100.00,
            currency="ILS",
        )

        # Get history
        result = await get_price_history("Test Product", days=1)

        assert result["total_count"] >= 1

    @pytest.mark.asyncio
    async def test_get_average_market_price_tool(self, setup_db):
        """Test get_average_market_price tool."""
        # Save multiple prices
        for price in [100.00, 110.00, 90.00]:
            await save_search_result(
                product_name="Test Product",
                url=f"https://example.com/product{price}",
                price=price,
                currency="ILS",
            )

        # Get average
        result = await get_average_market_price("Test Product", days=1)

        assert result["sample_size"] == 3
        assert result["average"] == 100.00
        assert result["min"] == 90.00
        assert result["max"] == 110.00


class TestPriceComparisonIntegration:
    """Integration tests for price comparison workflow."""

    @pytest.mark.asyncio
    async def test_compare_prices(self, sample_prices):
        """Test price comparison functionality."""
        result = await compare_prices(sample_prices)

        assert result["best_price"]["value"] == 4799.00
        assert result["worst_price"]["value"] == 5199.00
        assert result["potential_savings"] == 400.00

    @pytest.mark.asyncio
    async def test_compare_prices_empty(self):
        """Test price comparison with empty list."""
        result = await compare_prices([])

        assert result["best_price"] is None
        assert result["sample_size"] == 0 if "sample_size" in result else True


class TestEndToEndWorkflow:
    """End-to-end workflow tests."""

    @pytest.mark.asyncio
    async def test_price_extraction_workflow(self, sample_html):
        """Test complete price extraction workflow."""
        from src.tools.price_tools import normalize_product_name, parse_price
        from src.tools.scraping_tools import (
            extract_prices_from_html,
            extract_structured_data,
        )

        # Step 1: Extract structured data
        structured = await extract_structured_data(sample_html)
        assert len(structured["json_ld"]) > 0

        # Step 2: Extract prices
        prices = await extract_prices_from_html(sample_html)
        assert len(prices) > 0

        # Step 3: Parse the best price
        best_price = prices[0]
        parsed = await parse_price(f"₪{best_price['value']}")
        assert parsed["value"] == best_price["value"]

        # Step 4: Normalize product name
        product_name = structured["json_ld"][0].get("name", "")
        if product_name:
            normalized = await normalize_product_name(product_name)
            assert normalized["normalized"]

    @pytest.mark.asyncio
    async def test_cost_calculation_workflow(self):
        """Test complete cost calculation workflow."""
        from src.tools.price_tools import calculate_total_cost, parse_price

        # Parse original price
        price_result = await parse_price("₪4,999")
        assert price_result["value"] == 4999.0

        # Calculate total with Israeli VAT
        total = await calculate_total_cost(
            base_price=price_result["value"],
            shipping_cost=29.90,
            tax_rate=0.17,
            discount_percent=5,
        )

        # Verify calculation
        # Base: 4999
        # Discount: 249.95
        # After discount: 4749.05
        # Tax: 807.34 (17% of 4749.05)
        # Shipping: 29.90
        # Total: ~5586.29

        assert total["base_price"] == 4999.0
        assert total["discount"] == 249.95
        assert 5500 < total["total"] < 5600
