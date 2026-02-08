"""Pytest configuration and fixtures."""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Settings
from src.server.main import app, create_app
from src.utils.database import DatabaseManager


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with temporary database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Settings(
            HOST="127.0.0.1",
            PORT=8001,
            DEBUG=True,
            DATABASE_PATH=f"{tmpdir}/test_prices.db",
            SERPER_API_KEY="test_key",
            LOG_LEVEL="DEBUG",
        )


@pytest_asyncio.fixture
async def test_db(test_settings: Settings) -> AsyncGenerator[DatabaseManager, None]:
    """Create test database manager."""
    db = DatabaseManager(db_path=test_settings.DATABASE_PATH)
    await db.initialize()
    yield db


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create test client for sync tests."""
    with TestClient(app) as client:
        yield client


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def sample_html() -> str:
    """Sample HTML with price data for testing."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:price:amount" content="4999.00">
        <meta property="og:price:currency" content="ILS">
        <meta property="og:title" content="iPhone 15 Pro">
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "iPhone 15 Pro 256GB",
            "offers": {
                "@type": "Offer",
                "price": "4999.00",
                "priceCurrency": "ILS",
                "availability": "https://schema.org/InStock"
            }
        }
        </script>
    </head>
    <body>
        <div class="product">
            <h1>Apple iPhone 15 Pro 256GB Space Black</h1>
            <span class="price">₪4,999</span>
            <span class="original-price">₪5,499</span>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def sample_prices() -> list:
    """Sample price data for testing."""
    return [
        {"value": 4999.00, "currency": "ILS", "source": "Store A"},
        {"value": 4899.00, "currency": "ILS", "source": "Store B"},
        {"value": 5199.00, "currency": "ILS", "source": "Store C"},
        {"value": 4799.00, "currency": "ILS", "source": "Store D"},
        {"value": 5099.00, "currency": "ILS", "source": "Store E"},
    ]
