"""Identifier and serialization helpers for Omnifin.

The database stores UUID primary keys as 16-byte SQLite BLOB values. The domain
layer works with normal ``uuid.UUID`` objects.
"""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime
from hashlib import blake2b
from typing import Any
from uuid import UUID


def uuid7() -> UUID:
    """Return a UUIDv7-compatible value without requiring an external package.

    Layout: 48-bit Unix epoch milliseconds, version 7 marker, 12 bits random,
    RFC variant marker, and 62 additional random bits.
    """

    timestamp_ms = int(time.time_ns() // 1_000_000) & ((1 << 48) - 1)
    rand_a = secrets.randbits(12)
    rand_b = secrets.randbits(62)
    value = (
        (timestamp_ms << 80)
        | (0x7 << 76)
        | (rand_a << 64)
        | (0b10 << 62)
        | rand_b
    )
    return UUID(int=value)


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def parse_uuid(value: UUID | bytes | bytearray | memoryview | str) -> UUID:
    """Convert a SQLite/Python UUID representation to ``uuid.UUID``."""

    if isinstance(value, UUID):
        return value
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytearray):
        value = bytes(value)
    if isinstance(value, bytes):
        if len(value) != 16:
            raise ValueError(f"UUID BLOB values must contain 16 bytes, got {len(value)}")
        return UUID(bytes=value)
    return UUID(str(value))


def to_db_value(value: Any) -> Any:
    """Convert a domain value into a SQLite-compatible value."""

    if isinstance(value, UUID):
        return value.bytes
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    return value


def stable_hash_bytes(value: str | bytes) -> bytes:
    """Return a compact deterministic hash suitable for raw source rows/files."""

    if isinstance(value, str):
        value = value.encode("utf-8")
    return blake2b(value, digest_size=16).digest()
