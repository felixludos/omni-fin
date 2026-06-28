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
        self.conn.execute("PRAGMA foreign_keys = ON;")
        if self.initialize:
            init_db(self.conn)
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
        spec = MODEL_SPECS[model_cls.__name__]
        cursor = self.execute(
            f"SELECT 1 FROM {spec.table} WHERE {spec.pk} = ?", (to_db_value(key),)
        )
        return cursor.fetchone() is not None

    def find_by_unique(self, model_cls: type[T], column: str, value: Any) -> T | None:
        spec = MODEL_SPECS[model_cls.__name__]
        cursor = self.execute(
            f"SELECT * FROM {spec.table} WHERE {column} = ? LIMIT 1", (to_db_value(value),)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return model_cls(_session=self, _from_db=True, **row)  # type: ignore[call-arg]

    def all(self, model_cls: type[T], *, limit: int = 100, offset: int = 0) -> list[T]:
        spec = MODEL_SPECS[model_cls.__name__]
        cursor = self.execute(
            f"SELECT * FROM {spec.table} ORDER BY {spec.pk} LIMIT ? OFFSET ?", (limit, offset)
        )
        return [model_cls(_session=self, _from_db=True, **row) for row in cursor.fetchall()]  # type: ignore[call-arg]


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)")
    conn.commit()


def normalize_identity_value(value: Any) -> Any:
    if isinstance(value, (UUID, bytes, bytearray, memoryview)):
        try:
            return parse_uuid(value)
        except Exception:
            return value
    return value
