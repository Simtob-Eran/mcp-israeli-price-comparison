"""Server-Sent Events (SSE) handler for streaming MCP responses."""

import asyncio
import json
import logging
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from ..config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SSEEvent:
    """Represents a Server-Sent Event."""

    type: str
    data: Optional[Any] = None
    tool: Optional[str] = None
    message: Optional[str] = None
    id: Optional[str] = None
    retry: Optional[int] = None

    def format(self) -> str:
        """Format the event for SSE transmission.

        Returns:
            Formatted SSE event string.
        """
        lines = []

        if self.id:
            lines.append(f"id: {self.id}")

        if self.retry:
            lines.append(f"retry: {self.retry}")

        # Build event data
        event_data = {"type": self.type}

        if self.tool:
            event_data["tool"] = self.tool

        if self.message:
            event_data["message"] = self.message

        if self.data is not None:
            event_data["data"] = self.data

        lines.append(f"data: {json.dumps(event_data)}")
        lines.append("")  # Empty line to end event

        return "\n".join(lines) + "\n"


@dataclass
class SSESession:
    """Represents an active SSE session."""

    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    last_event_id: int = 0
    events: List[SSEEvent] = field(default_factory=list)

    def next_event_id(self) -> str:
        """Generate next event ID.

        Returns:
            Unique event ID string.
        """
        self.last_event_id += 1
        return f"{self.session_id}-{self.last_event_id}"


class SSEHandler:
    """Handler for managing SSE connections and streaming."""

    def __init__(self):
        """Initialize SSE handler."""
        self.settings = get_settings()
        self.sessions: Dict[str, SSESession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def create_session(self) -> SSESession:
        """Create a new SSE session.

        Returns:
            New SSESession instance.
        """
        session_id = str(uuid.uuid4())
        session = SSESession(session_id=session_id)
        self.sessions[session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[SSESession]:
        """Get an existing session.

        Args:
            session_id: Session ID to look up.

        Returns:
            SSESession or None if not found.
        """
        return self.sessions.get(session_id)

    def remove_session(self, session_id: str) -> None:
        """Remove a session.

        Args:
            session_id: Session ID to remove.
        """
        self.sessions.pop(session_id, None)

    async def cleanup_old_sessions(self, max_age_seconds: int = 3600) -> None:
        """Remove sessions older than max_age.

        Args:
            max_age_seconds: Maximum session age in seconds.
        """
        now = datetime.now()
        expired = [
            sid
            for sid, session in self.sessions.items()
            if (now - session.created_at).total_seconds() > max_age_seconds
        ]
        for sid in expired:
            self.remove_session(sid)

    def format_event(
        self,
        event_type: str,
        data: Optional[Any] = None,
        tool: Optional[str] = None,
        message: Optional[str] = None,
        session: Optional[SSESession] = None,
    ) -> str:
        """Format an SSE event.

        Args:
            event_type: Type of event (start, progress, result, error, complete).
            data: Event data payload.
            tool: Tool name (for tool-related events).
            message: Human-readable message.
            session: Optional session for event ID tracking.

        Returns:
            Formatted SSE event string.
        """
        event = SSEEvent(
            type=event_type,
            data=data,
            tool=tool,
            message=message,
            id=session.next_event_id() if session else None,
            retry=self.settings.SSE_RETRY_TIMEOUT,
        )

        if session:
            session.events.append(event)

        return event.format()


async def stream_tool_result(
    tool_name: str,
    arguments: Dict[str, Any],
    executor: Callable,
    session: Optional[SSESession] = None,
) -> AsyncGenerator[str, None]:
    """Stream tool execution results via SSE.

    Executes a tool and streams progress and results as SSE events.

    Event types:
    - start: Tool execution beginning
    - progress: Optional progress updates during execution
    - result: Final tool result
    - error: Error occurred during execution
    - complete: Execution finished

    Args:
        tool_name: Name of the tool being executed.
        arguments: Tool arguments dictionary.
        executor: Async callable that executes the tool.
        session: Optional SSE session for event tracking.

    Yields:
        Formatted SSE event strings.

    Example:
        >>> async def my_tool(**kwargs):
        ...     return {"result": "success"}
        >>>
        >>> async for event in stream_tool_result("my_tool", {"arg": "value"}, my_tool):
        ...     print(event)
    """
    handler = SSEHandler()
    settings = get_settings()

    # Send start event
    yield handler.format_event(
        event_type="start",
        tool=tool_name,
        message=f"Starting execution of {tool_name}",
        session=session,
    )

    try:
        # Send progress event
        yield handler.format_event(
            event_type="progress",
            tool=tool_name,
            message="Executing tool...",
            session=session,
        )

        # Execute the tool
        result = await executor(**arguments)

        # Send result event
        yield handler.format_event(
            event_type="result",
            tool=tool_name,
            data=result,
            message="Tool executed successfully",
            session=session,
        )

    except Exception as e:
        logger.error(f"Tool execution error: {tool_name} - {e}")
        logger.debug(traceback.format_exc())

        # Send error event
        yield handler.format_event(
            event_type="error",
            tool=tool_name,
            message=str(e),
            data={"error_type": type(e).__name__},
            session=session,
        )

    finally:
        # Send complete event
        yield handler.format_event(
            event_type="complete",
            tool=tool_name,
            session=session,
        )


async def stream_keepalive(
    interval: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Generate keepalive events for SSE connection.

    Yields comment events periodically to keep the connection alive.

    Args:
        interval: Seconds between keepalive events. Default from settings.

    Yields:
        SSE comment strings (": keepalive").
    """
    settings = get_settings()
    interval = interval or settings.SSE_KEEPALIVE_INTERVAL

    while True:
        await asyncio.sleep(interval)
        yield ": keepalive\n\n"


async def stream_mcp_response(
    request_id: Optional[str],
    method: str,
    result: Optional[Any] = None,
    error: Optional[Dict[str, Any]] = None,
    session: Optional[SSESession] = None,
) -> AsyncGenerator[str, None]:
    """Stream an MCP JSON-RPC response via SSE.

    Formats and streams a complete MCP response.

    Args:
        request_id: JSON-RPC request ID.
        method: Method that was called.
        result: Success result data.
        error: Error data if failed.
        session: Optional SSE session.

    Yields:
        Formatted SSE event strings.
    """
    handler = SSEHandler()

    response = {
        "jsonrpc": "2.0",
        "id": request_id,
    }

    if error:
        response["error"] = error
        yield handler.format_event(
            event_type="error",
            data=response,
            message=error.get("message", "Unknown error"),
            session=session,
        )
    else:
        response["result"] = result
        yield handler.format_event(
            event_type="result",
            data=response,
            session=session,
        )

    yield handler.format_event(
        event_type="complete",
        session=session,
    )
