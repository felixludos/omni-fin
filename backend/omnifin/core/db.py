"""SQLite session management for Omnifin."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, TypeVar
from uuid import UUID

from omnifin.core.ids import parse_uuid, to_db_value
from omnifin.core.registry import MODEL_SPECS

T = TypeVar("T")

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PACKAGE_ROOT / "db" / "schema.sql"


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


class DatabaseSession:
    """Context-managed SQLite connection plus a session-scoped identity map."""

    def __init__(self, db_path: str | Path = "omnifin.db", *, initialize: bool = True):
        self.db_path = Path(db_path)
        self.initialize = initialize
        self.conn: sqlite3.Connection | None = None
        self.identity_map: dict[type, dict[Any, Any]] = {}
        self.natural_key_map: dict[tuple[type, str, Any], Any] = {}

    def __enter__(self) -> "DatabaseSession":
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = dict_factory
        if self.initialize:
            init_db(self.conn)
        # Re-enable foreign keys -- PRAGMA is reset to OFF by executescript.
        self.conn.execute("PRAGMA foreign_keys = ON;")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.conn is not None:
            self.conn.close()
        self.conn = None
        self.identity_map.clear()
        self.natural_key_map.clear()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        if self.conn is None:
            raise RuntimeError("DatabaseSession is not open")
        return self.conn.execute(sql, tuple(params))

    def commit(self) -> None:
        if self.conn is None:
            raise RuntimeError("DatabaseSession is not open")
        self.conn.commit()

    def rollback(self) -> None:
        if self.conn is None:
            raise RuntimeError("DatabaseSession is not open")
        self.conn.rollback()

    def get(self, model_cls: type[T], key: Any) -> T | None:
        """Load one model by primary key, returning the session singleton if present."""

        from omnifin.models.domain import DomainModel

        custom_get = getattr(model_cls, "db_get", None)
        if callable(custom_get):
            return custom_get(self, key)

        spec = MODEL_SPECS[model_cls.__name__]
        normalized_key = normalize_identity_value(key)
        if model_cls in self.identity_map and normalized_key in self.identity_map[model_cls]:
            obj = self.identity_map[model_cls][normalized_key]
            if isinstance(obj, DomainModel) and not obj._loaded:
                obj._hydrate()
            return obj

        cursor = self.execute(
            f"SELECT * FROM {spec.table} WHERE {spec.pk} = ?", (to_db_value(normalized_key),)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return model_cls(_session=self, _from_db=True, **row)  # type: ignore[call-arg]

    def exists(self, model_cls: type, key: Any) -> bool:
        custom_exists = getattr(model_cls, "db_exists", None)
        if callable(custom_exists):
            return bool(custom_exists(self, key))
        spec = MODEL_SPECS[model_cls.__name__]
        cursor = self.execute(
            f"SELECT 1 FROM {spec.table} WHERE {spec.pk} = ?", (to_db_value(key),)
        )
        return cursor.fetchone() is not None

    def find_by_unique(self, model_cls: type[T], column: str, value: Any) -> T | None:
        custom_find = getattr(model_cls, "db_find_by_unique", None)
        if callable(custom_find):
            return custom_find(self, column, value)
        spec = MODEL_SPECS[model_cls.__name__]
        cursor = self.execute(
            f"SELECT * FROM {spec.table} WHERE {column} = ? LIMIT 1", (to_db_value(value),)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return model_cls(_session=self, _from_db=True, **row)  # type: ignore[call-arg]

    def all(self, model_cls: type[T], *, limit: int = 100, offset: int = 0) -> list[T]:
        custom_all = getattr(model_cls, "db_all", None)
        if callable(custom_all):
            return custom_all(self, limit=limit, offset=offset)
        spec = MODEL_SPECS[model_cls.__name__]
        cursor = self.execute(
            f"SELECT * FROM {spec.table} ORDER BY {spec.pk} LIMIT ? OFFSET ?", (limit, offset)
        )
        return [model_cls(_session=self, _from_db=True, **row) for row in cursor.fetchall()]  # type: ignore[call-arg]


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database with the current schema and run migrations."""

    # Commit any open transaction first so executescript runs in a clean scope.
    conn.commit()

    # Apply the base schema (CREATE TABLE IF NOT EXISTS won't overwrite existing tables).
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    except sqlite3.OperationalError as exc:
        # executescript may fail if a statement references an unsupported feature;
        # swallow and continue -- migration logic below adds any missing columns.
        pass

    # Re-enable foreign keys -- PRAGMA is reset to OFF by executescript.
    conn.execute("PRAGMA foreign_keys = ON;")

    # Ensure known-missing columns exist on existing tables before running
    # migrations. If events.table already exists without 'type', CREATE TABLE
    # IF NOT EXISTS above won't add it -- the column stays missing and later
    # statements fail with "no such column: type". Adding it here is safe
    # regardless of schema state.
    if not _column_exists(conn, "events", "type"):
        conn.execute("ALTER TABLE events ADD COLUMN type TEXT NOT NULL DEFAULT 'unknown'")

    # Run any pending migrations on the main connection.
    _apply_pending_migrations(conn)

    # Auto-seed basic objects (tags, accounts, assets) if the database is fresh.
    _seed_if_empty(conn)

    conn.commit()


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table.

    Handles both dict and tuple row_factory configurations by reading the 'name'
    field from PRAGMA results (which is always available as the first column).
    """
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    # Save current factory, temporarily switch to index-based access for safety.
    prev_factory = conn.row_factory
    conn.row_factory = None
    rows = cursor.fetchall()
    conn.row_factory = prev_factory

    if not rows:
        return False
    sample = rows[0]
    if isinstance(sample, dict):
        columns = [r["name"] for r in rows]
    else:
        # (cid, name, type, notnull, dflt_value, pk) -> index 1 is the column name.
        columns = [r[1] for r in rows]
    return column_name in columns


def _apply_pending_migrations(conn: sqlite3.Connection) -> None:
    """Apply database migrations to ensure schema is up-to-date."""

    # Ensure the migrations table exists (schema.sql creates it, but be defensive).
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
        ") STRICT"
    )

    # Temporarily clear the row_factory so aggregate results come back as plain tuples.
    # This is needed because dict_factory would return dicts, but we access by index here.
    previous_factory = conn.row_factory
    conn.row_factory = None

    raw_cursor = conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
    )
    current_version = next(iter(next(raw_cursor)), 0)
    conn.row_factory = previous_factory

    # Migration 1: Add 'type' column to events table if missing.
    if current_version < 1 and not _column_exists(conn, "events", "type"):
        conn.execute(
            f"ALTER TABLE events ADD COLUMN type TEXT DEFAULT 'unknown'"
        )
        conn.execute("INSERT OR REPLACE INTO schema_migrations(version) VALUES (1)")


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """Auto-seed tags, accounts, and assets if their tables are empty.

    Called after migrations during ``init_db()`` so that a freshly initialized
    database is immediately usable without manual setup steps.
    """
    from omnifin.db.seeding import _seed_if_empty as do_seed  # avoid circular imports at module level
    do_seed(conn)


def normalize_identity_value(value: Any) -> Any:
    if isinstance(value, (UUID, bytes, bytearray, memoryview)):
        try:
            return parse_uuid(value)
        except Exception:
            return value
    return value