"""Domain-specific exceptions."""

from __future__ import annotations


class OmnifinError(Exception):
    """Base exception for Omnifin failures."""


class LedgerIntegrityError(OmnifinError):
    """Raised when a planned ledger write would violate integrity rules."""


class MissingDatabaseSessionError(OmnifinError):
    """Raised when a persistence operation needs a database session."""


class ReadOnlyModelError(OmnifinError):
    """Raised when code attempts to mutate a read-only domain object."""
