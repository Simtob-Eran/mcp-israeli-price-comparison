"""Tests for MCP tools."""

import pytest
import pytest_asyncio

from src.tools.price_tools import (
    calculate_total_cost,
    detect_product_specs,
    normalize_product_name,
    parse_price,
)
from src.tools.scraping_tools import (
    extract_prices_from_html,
    extract_structured_data,
)
from src.utils.normalizer import TextNormalizer
from src.utils.parser import PriceParser


class TestPriceParser:
    """Tests for price parsing utilities."""

    def test_parse_ils_with_symbol(self):
        """Test parsing Israeli Shekel with symbol."""
        parser = PriceParser()
        result = parser.parse("₪1,234.56")

        assert result is not None
        assert result.value == 1234.56
        assert result.currency == "ILS"

    def test_parse_ils_with_text(self):
        """Test parsing Israeli Shekel with Hebrew text."""
        parser = PriceParser()
        result = parser.parse("1234 ש״ח")

        assert result is not None
        assert result.value == 1234.0
        assert result.currency == "ILS"

    def test_parse_usd(self):
        """Test parsing US Dollar."""
        parser = PriceParser()
        result = parser.parse("$1,234.56")

        assert result is not None
        assert result.value == 1234.56
        assert result.currency == "USD"

    def test_parse_euro_format(self):
        """Test parsing European format with comma decimal."""
        parser = PriceParser()
        result = parser.parse("1.234,56 €")

        assert result is not None
        assert result.value == 1234.56
        assert result.currency == "EUR"

    def test_parse_with_currency_hint(self):
        """Test parsing with currency hint."""
        parser = PriceParser()
        result = parser.parse("1234.56", currency_hint="GBP")

        assert result is not None
        assert result.value == 1234.56
        assert result.currency == "GBP"

    def test_extract_all_prices(self):
        """Test extracting multiple prices from text."""
        parser = PriceParser()
        text = "Price: ₪4,999 or $1,299 with shipping"
        results = parser.extract_all_prices(text)

        assert len(results) >= 2


class TestTextNormalizer:
    """Tests for text normalization utilities."""

    def test_normalize_product_name(self):
        """Test basic product name normalization."""
        normalizer = TextNormalizer()
        result = normalizer.normalize("Apple iPhone 15 Pro Max 256GB")

        assert result.normalized
        assert result.brand == "Apple"
        assert "smartphone" in result.category_hints

    def test_detect_brand(self):
        """Test brand detection."""
        normalizer = TextNormalizer()
        result = normalizer.normalize("Samsung Galaxy S24 Ultra")

        assert result.brand == "Samsung"

    def test_detect_categories(self):
        """Test category detection."""
        normalizer = TextNormalizer()
        result = normalizer.normalize("MacBook Pro 14 inch M3")

        assert "laptop" in result.category_hints

    def test_extract_specs(self):
        """Test specification extraction."""
        normalizer = TextNormalizer()
        specs = normalizer.extract_specs("16GB RAM 512GB SSD 14 inch display")

        assert specs.memory == "16GB"
        assert specs.storage is not None

    def test_remove_stopwords(self):
        """Test stopword removal."""
        normalizer = TextNormalizer(remove_stopwords=True)
        result = normalizer.normalize("The new Apple iPhone")

        assert "the" not in result.normalized.lower()
        assert "new" not in result.normalized.lower()


class TestPriceTools:
    """Tests for price intelligence tools."""

    @pytest.mark.asyncio
    async def test_parse_price_tool(self):
        """Test parse_price tool."""
        result = await parse_price("₪4,999.00")

        assert result["value"] == 4999.0
        assert result["currency"] == "ILS"

    @pytest.mark.asyncio
    async def test_normalize_product_name_tool(self):
        """Test normalize_product_name tool."""
        result = await normalize_product_name("Apple iPhone 15 Pro 256GB Black")

        assert result["normalized"]
        assert result["brand"] == "Apple"
        assert result["original"] == "Apple iPhone 15 Pro 256GB Black"

    @pytest.mark.asyncio
    async def test_detect_product_specs_tool(self):
        """Test detect_product_specs tool."""
        result = await detect_product_specs(
            "iPhone 15 Pro 256GB 6.1 inch A17 Pro chip Space Black"
        )

        assert result["storage"] is not None
        assert result["color"] is not None

    @pytest.mark.asyncio
    async def test_calculate_total_cost_basic(self):
        """Test basic total cost calculation."""
        result = await calculate_total_cost(base_price=1000.0)

        assert result["base_price"] == 1000.0
        assert result["total"] == 1000.0
        assert result["currency"] == "ILS"

    @pytest.mark.asyncio
    async def test_calculate_total_cost_with_shipping(self):
        """Test total cost with shipping."""
        result = await calculate_total_cost(
            base_price=1000.0,
            shipping_cost=50.0,
        )

        assert result["shipping"] == 50.0
        assert result["total"] == 1050.0

    @pytest.mark.asyncio
    async def test_calculate_total_cost_with_tax(self):
        """Test total cost with tax."""
        result = await calculate_total_cost(
            base_price=1000.0,
            tax_rate=0.17,
        )

        assert result["tax"] == 170.0
        assert result["total"] == 1170.0

    @pytest.mark.asyncio
    async def test_calculate_total_cost_with_discount(self):
        """Test total cost with discount."""
        result = await calculate_total_cost(
            base_price=1000.0,
            discount_percent=10.0,
        )

        assert result["discount"] == 100.0
        assert result["discounted_price"] == 900.0
        assert result["total"] == 900.0

    @pytest.mark.asyncio
    async def test_calculate_total_cost_full(self):
        """Test full total cost calculation."""
        result = await calculate_total_cost(
            base_price=1000.0,
            shipping_cost=50.0,
            tax_rate=0.17,
            discount_percent=10.0,
            additional_fees={"handling": 20.0},
        )

        # 1000 - 100 (discount) = 900
        # 900 * 0.17 = 153 (tax)
        # 900 + 50 + 153 + 20 = 1123
        assert result["total"] == 1123.0


class TestScrapingTools:
    """Tests for web scraping tools."""

    @pytest.mark.asyncio
    async def test_extract_structured_data(self, sample_html):
        """Test structured data extraction."""
        result = await extract_structured_data(sample_html)

        assert "json_ld" in result
        assert "opengraph" in result
        assert len(result["json_ld"]) > 0

    @pytest.mark.asyncio
    async def test_extract_json_ld_product(self, sample_html):
        """Test JSON-LD product extraction."""
        result = await extract_structured_data(sample_html, ["json-ld"])

        json_ld = result["json_ld"]
        assert len(json_ld) > 0
        assert json_ld[0]["@type"] == "Product"

    @pytest.mark.asyncio
    async def test_extract_opengraph(self, sample_html):
        """Test Open Graph extraction."""
        result = await extract_structured_data(sample_html, ["opengraph"])

        og = result["opengraph"]
        assert og.get("price_amount") == "4999.00"
        assert og.get("price_currency") == "ILS"

    @pytest.mark.asyncio
    async def test_extract_prices_from_html(self, sample_html):
        """Test price extraction from HTML."""
        result = await extract_prices_from_html(sample_html)

        assert len(result) > 0
        # Should find the price from JSON-LD with high confidence
        high_confidence = [p for p in result if p["confidence"] > 0.8]
        assert len(high_confidence) > 0

    @pytest.mark.asyncio
    async def test_extract_prices_confidence_ordering(self, sample_html):
        """Test that prices are ordered by confidence."""
        result = await extract_prices_from_html(sample_html)

        if len(result) > 1:
            for i in range(len(result) - 1):
                assert result[i]["confidence"] >= result[i + 1]["confidence"]
