"""Middleware components for the MCP server."""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from ..config import get_settings

logger = logging.getLogger(__name__)


def setup_cors(app: FastAPI) -> None:
    """Configure CORS middleware for the FastAPI app.

    Allows cross-origin requests for API access from web clients.

    Args:
        app: FastAPI application instance.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining"],
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests and responses."""

    def __init__(self, app: ASGIApp, log_body: bool = False):
        """Initialize logging middleware.

        Args:
            app: ASGI application.
            log_body: Whether to log request/response bodies.
        """
        super().__init__(app)
        self.log_body = log_body

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details.

        Args:
            request: Incoming request.
            call_next: Next middleware/route handler.

        Returns:
            Response from the handler.
        """
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        # Log request
        start_time = time.time()
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"- Client: {request.client.host if request.client else 'unknown'}"
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Log response
            logger.info(
                f"[{request_id}] {request.method} {request.url.path} "
                f"- Status: {response.status_code} - Duration: {duration:.3f}s"
            )

            # Add request ID header
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"[{request_id}] {request.method} {request.url.path} "
                f"- Error: {str(e)} - Duration: {duration:.3f}s"
            )
            raise


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting requests."""

    def __init__(
        self,
        app: ASGIApp,
        requests_per_window: Optional[int] = None,
        window_seconds: Optional[int] = None,
    ):
        """Initialize rate limiting middleware.

        Args:
            app: ASGI application.
            requests_per_window: Max requests allowed per window.
            window_seconds: Window duration in seconds.
        """
        super().__init__(app)
        settings = get_settings()
        self.requests_per_window = requests_per_window or settings.RATE_LIMIT_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW
        self.request_counts: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _get_client_key(self, request: Request) -> str:
        """Get unique key for rate limiting client.

        Args:
            request: Incoming request.

        Returns:
            Client identifier string.
        """
        # Use client IP, or forwarded IP if behind proxy
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        if request.client:
            return request.client.host

        return "unknown"

    async def _is_rate_limited(self, client_key: str) -> Tuple[bool, int]:
        """Check if client is rate limited.

        Args:
            client_key: Client identifier.

        Returns:
            Tuple of (is_limited, remaining_requests).
        """
        async with self._lock:
            now = time.time()
            window_start = now - self.window_seconds

            # Clean old entries
            self.request_counts[client_key] = [
                ts for ts in self.request_counts[client_key] if ts > window_start
            ]

            current_count = len(self.request_counts[client_key])
            remaining = max(0, self.requests_per_window - current_count)

            if current_count >= self.requests_per_window:
                return True, remaining

            # Add current request
            self.request_counts[client_key].append(now)
            return False, remaining - 1

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with rate limiting.

        Args:
            request: Incoming request.
            call_next: Next middleware/route handler.

        Returns:
            Response from handler or 429 if rate limited.
        """
        # Skip rate limiting for health checks
        if request.url.path in ["/health", "/healthz", "/"]:
            return await call_next(request)

        client_key = self._get_client_key(request)
        is_limited, remaining = await self._is_rate_limited(client_key)

        if is_limited:
            logger.warning(f"Rate limit exceeded for client: {client_key}")
            return Response(
                content='{"error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_window),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": str(self.window_seconds),
                },
            )

        response = await call_next(request)

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_window)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Middleware for consistent error handling."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with error handling.

        Args:
            request: Incoming request.
            call_next: Next middleware/route handler.

        Returns:
            Response from handler or error response.
        """
        try:
            return await call_next(request)

        except Exception as e:
            request_id = getattr(request.state, "request_id", "unknown")
            logger.exception(f"[{request_id}] Unhandled exception: {e}")

            return Response(
                content=f'{{"error": "Internal server error", "request_id": "{request_id}"}}',
                status_code=500,
                media_type="application/json",
            )


def setup_middleware(app: FastAPI) -> None:
    """Configure all middleware for the FastAPI app.

    Adds middleware in the correct order (reverse of execution order):
    1. CORS (executed last)
    2. Error handling
    3. Rate limiting
    4. Request logging (executed first)

    Args:
        app: FastAPI application instance.
    """
    # Add middleware in reverse order of execution
    setup_cors(app)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)


def setup_logging() -> None:
    """Configure application logging."""
    settings = get_settings()

    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper()),
        format=settings.LOG_FORMAT,
    )

    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
