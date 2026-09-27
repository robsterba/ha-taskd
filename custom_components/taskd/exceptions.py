"""Exceptions for the taskd integration."""

from __future__ import annotations


class TaskdError(Exception):
    """Base exception for the taskd integration."""


class TaskdConnectionError(TaskdError):
    """Raised when the taskd server cannot be reached."""


class TaskdApiError(TaskdError):
    """Raised when the taskd API returns an HTTP error (non-404)."""

    def __init__(self, status: int, detail: str) -> None:
        """Initialize the error."""
        super().__init__(f"taskd API error {status}: {detail}")
        self.status = status
        self.detail = detail


class TaskdItemNotFoundError(TaskdError):
    """Raised when a taskd task does not exist (HTTP 404)."""
