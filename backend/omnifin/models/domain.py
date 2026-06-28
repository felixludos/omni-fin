"""High-level Omnifin domain model.

This file intentionally does not use an ORM. It provides a thin, explicit bridge
between ergonomic Pydantic domain objects and normalized SQLite tables:

* UUIDv7-like IDs are generated in Python and stored as SQLite BLOBs.
* Session-scoped identity maps make objects singletons by primary key.
* Relations are represented as high-level objects and serialized to foreign keys.
* Staged tag/comment/entity/event edits are visible locally and flushed by
  ``Report.save(...)``.
* ``Report.plan(...)`` performs the same graph traversal as ``save(...)`` without
  mutating SQLite.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any, Iterable, Literal, Optional, Self
from uuid import UUID
import sqlite3
import weakref

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from omnifin.core.errors import LedgerIntegrityError, MissingDatabaseSessionError, ReadOnlyModelError
from omnifin.core.ids import parse_uuid, to_db_value, utcnow, uuid7
from omnifin.core.registry import (
    COERCION_KEYS,
    MODEL_SPECS,
    NATURAL_KEY_FIELDS,
    RELATION_SPECS,
    SQL_TO_MODEL_FIELDS,
)

DOMAIN_CLASSES: dict[str, type["DomainModel"]] = {}
GLOBAL_IDENTITY_MAP: dict[type, dict[Any, "DomainModel"]] = defaultdict(dict)


def _safe_uuid(value: Any) -> Any:
    if isinstance(value, (UUID, bytes, bytearray, memoryview)):
        try:
            return parse_uuid(value)
        except Exception:
            return value
    return value


def _identity_cache_key(cls: type, data: dict[str, Any]) -> Any | None:
    spec = MODEL_SPECS.get(cls.__name__)
    if spec is None:
        return None

    # Prefer the real primary key if present.
    pk_candidates = [spec.identity_field, spec.pk]
    for name in pk_candidates:
        if name in data and data[name] is not None:
            value = _safe_uuid(data[name])
            return ("pk", value)

    # Some tables also have a stable natural key useful before an id is known.
    for field in NATURAL_KEY_FIELDS.get(cls.__name__, ()):  # e.g. Tag(name="tax")
        if field in data and data[field] is not None:
            value = data[field]
            if isinstance(value, str):
                value = value.strip().lower()
            return ("natural", field, value)
    return None


def _all_identity_keys(obj: "DomainModel") -> list[Any]:
    keys: list[Any] = []
    spec = MODEL_SPECS.get(obj.__class__.__name__)
    if spec is None:
        return keys
    identity_value = getattr(obj, spec.identity_field, None)
    if identity_value is not None:
        keys.append(("pk", _safe_uuid(identity_value)))
    for field in NATURAL_KEY_FIELDS.get(obj.__class__.__name__, ()):  # natural aliases
        value = getattr(obj, field, None)
        if value is not None:
            if isinstance(value, str):
                value = value.strip().lower()
            keys.append(("natural", field, value))
    return keys


class IdentityMapMeta(type(BaseModel)):
    """Metaclass that returns one object per primary key per session."""

    def __call__(cls, *args: Any, **kwargs: Any):
        if len(args) > 1:
            raise TypeError(f"{cls.__name__} accepts at most one positional value for coercion")
        if len(args) == 1:
            coercion_key = COERCION_KEYS.get(cls.__name__)
            if coercion_key is None:
                spec = MODEL_SPECS.get(cls.__name__)
                coercion_key = spec.identity_field if spec else "id"
            kwargs.setdefault(coercion_key, args[0])
            args = ()

        session = kwargs.get("_session") or kwargs.get("session")
        cache = session.identity_map if session is not None else GLOBAL_IDENTITY_MAP
        cache.setdefault(cls, {})

        key = _identity_cache_key(cls, kwargs)
        if key is not None and key in cache[cls]:
            existing = cache[cls][key]
            existing._merge_raw_data(kwargs, from_db=bool(kwargs.get("_from_db")))
            if session is not None and existing._session is None:
                existing._session = session
            return existing

        instance = super().__call__(*args, **kwargs)
        for final_key in _all_identity_keys(instance):
            cache[cls][final_key] = instance
        return instance


class PlanRecord(BaseModel):
    model: str
    table: str
    key: str
    action: Literal["insert", "update", "unchanged", "error"]
    missing_fields: list[str] = Field(default_factory=list)


class RelationPlanRecord(BaseModel):
    owner_model: str
    relation: str
    table: str
    action: Literal["insert", "delete"]
    owner_key: str
    related_key: str


class PlanSummary(BaseModel):
    is_valid: bool = True
    inserts: dict[str, int] = Field(default_factory=dict)
    updates: dict[str, int] = Field(default_factory=dict)
    unchanged: dict[str, int] = Field(default_factory=dict)
    relation_inserts: dict[str, int] = Field(default_factory=dict)
    relation_deletes: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    records: list[PlanRecord] = Field(default_factory=list)
    relations: list[RelationPlanRecord] = Field(default_factory=list)

    def add_error(self, message: str) -> None:
        self.is_valid = False
        self.errors.append(message)


class DomainModel(BaseModel, metaclass=IdentityMapMeta):
    """Base object with identity-map, lazy-loading, and staged-relation support."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        validate_assignment=False,
        extra="ignore",
    )

    _session: Any = PrivateAttr(default=None)
    _loaded: bool = PrivateAttr(default=True)
    _readonly: bool = PrivateAttr(default=False)
    _hydrating: bool = PrivateAttr(default=False)
    _staged_adds: dict[str, dict[Any, Any]] = PrivateAttr(default_factory=lambda: defaultdict(dict))
    _staged_removes: dict[str, dict[Any, Any]] = PrivateAttr(default_factory=lambda: defaultdict(dict))
    _relation_cache: dict[str, dict[Any, Any]] = PrivateAttr(default_factory=dict)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__name__ not in {"Tagable", "Commentable"}:
            DOMAIN_CLASSES[cls.__name__] = cls

    def __init__(
        self,
        *,
        _session: Any = None,
        session: Any = None,
        _from_db: bool = False,
        _loaded: bool | None = None,
        _readonly: bool = False,
        **data: Any,
    ):
        super().__init__(**data)
        self._session = _session or session
        if _loaded is not None:
            self._loaded = _loaded
        else:
            self._loaded = bool(_from_db) or not self._is_identity_only()
        self._readonly = _readonly
        self._register_session_identity()
        self._propagate_session()

    @model_validator(mode="before")
    @classmethod
    def _normalize_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)

        # Translate SQL column names into high-level field names.
        for sql_col, model_field in SQL_TO_MODEL_FIELDS.get(cls.__name__, {}).items():
            if sql_col in normalized and model_field not in normalized:
                normalized[model_field] = normalized.pop(sql_col)

        for field_name, value in list(normalized.items()):
            if field_name.startswith("_"):
                continue
            normalized[field_name] = cls._coerce_field_value(field_name, value)
        return normalized

    @classmethod
    def _coerce_field_value(cls, field_name: str, value: Any) -> Any:
        if value is None:
            return None
        relation_model = {
            "recorded": "Report",
            "account": "Account",
            "sender": "Account",
            "receiver": "Account",
            "unit": "Asset",
            "location": "Location",
        }.get(field_name)
        if relation_model is None:
            # UUID fields stored as blobs.
            if field_name == "id":
                return _safe_uuid(value)
            return value

        target_cls = DOMAIN_CLASSES.get(relation_model)
        if target_cls is None:
            return value
        if isinstance(value, target_cls):
            return value
        if isinstance(value, dict):
            return target_cls(**value)

        spec = MODEL_SPECS[relation_model]
        if relation_model == "Asset":
            return target_cls(symbol=str(value))
        if isinstance(value, (UUID, bytes, bytearray, memoryview)):
            return target_cls(id=parse_uuid(value))
        # Strings passed to Account/Report/etc. are treated as natural names in user code.
        coercion_key = COERCION_KEYS.get(relation_model, spec.identity_field)
        return target_cls(**{coercion_key: value})

    def __getattribute__(self, name: str) -> Any:
        if not name.startswith("_"):
            try:
                model_fields = type(self).model_fields
                if name in model_fields:
                    spec = MODEL_SPECS.get(self.__class__.__name__)
                    identity_field = spec.identity_field if spec else "id"
                    loaded = object.__getattribute__(self, "__pydantic_private__").get("_loaded", True)
                    hydrating = object.__getattribute__(self, "__pydantic_private__").get("_hydrating", False)
                    if not loaded and not hydrating and name != identity_field:
                        self._hydrate()
            except Exception:
                pass
        return super().__getattribute__(name)

    def __repr__(self) -> str:
        return self.model_repr(load_lazy=False)

    def model_repr(self, *, load_lazy: bool = False) -> str:
        spec = MODEL_SPECS.get(self.__class__.__name__)
        identity_field = spec.identity_field if spec else "id"
        pieces = []
        for field_name in type(self).model_fields:
            if field_name != identity_field and not self._loaded and not load_lazy:
                pieces.append(f"{field_name}=<UNLOADED>")
                continue
            value = getattr(self, field_name)
            if isinstance(value, DomainModel):
                rel_spec = MODEL_SPECS.get(value.__class__.__name__)
                rel_field = rel_spec.identity_field if rel_spec else "id"
                rel_key = getattr(value, rel_field, None)
                pieces.append(f"{field_name}={value.__class__.__name__}({rel_field}={rel_key!r})")
            else:
                pieces.append(f"{field_name}={value!r}")
        return f"{self.__class__.__name__}({', '.join(pieces)})"

    def _merge_raw_data(self, data: dict[str, Any], *, from_db: bool = False) -> None:
        normalized = self.__class__._normalize_input(data)
        for field_name, value in normalized.items():
            if field_name.startswith("_") or field_name not in type(self).model_fields:
                continue
            current = getattr(self, field_name, None)
            if value is None:
                continue
            if current is None or from_db:
                object.__setattr__(self, field_name, value)
        if from_db:
            self._loaded = True
        self._propagate_session()

    def _register_session_identity(self) -> None:
        if self._session is None:
            return
        self._session.identity_map.setdefault(self.__class__, {})
        for key in _all_identity_keys(self):
            self._session.identity_map[self.__class__][key] = self

    def _propagate_session(self) -> None:
        if self._session is None:
            return
        self._register_session_identity()
        for value in self.__dict__.values():
            if isinstance(value, DomainModel) and value._session is None:
                value._session = self._session
                for key in _all_identity_keys(value):
                    self._session.identity_map.setdefault(value.__class__, {})[key] = value

    def _is_identity_only(self) -> bool:
        spec = MODEL_SPECS.get(self.__class__.__name__)
        if spec is None:
            return False
        public_values = {
            name: getattr(self, name, None)
            for name in type(self).model_fields
            if getattr(self, name, None) is not None
        }
        return set(public_values.keys()).issubset({spec.identity_field})

    def _pk_value(self) -> Any:
        spec = MODEL_SPECS[self.__class__.__name__]
        return getattr(self, spec.identity_field)

    def _db_pk_value(self) -> Any:
        return to_db_value(self._pk_value())

    def _hydrate(self) -> bool:
        if self._session is None or self._loaded or self._hydrating:
            return self._loaded
        spec = MODEL_SPECS.get(self.__class__.__name__)
        if spec is None:
            return False
        self._hydrating = True
        try:
            row = self._session.execute(
                f"SELECT * FROM {spec.table} WHERE {spec.pk} = ?", (self._db_pk_value(),)
            ).fetchone()
            if row is None:
                self._loaded = True
                return False
            self._merge_raw_data(row, from_db=True)
            self._loaded = True
            return True
        finally:
            self._hydrating = False

    def _ensure_mutable(self) -> None:
        if self._readonly:
            raise ReadOnlyModelError(f"{self.__class__.__name__} is read-only")

    def _existing_row(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        spec = MODEL_SPECS[self.__class__.__name__]
        return self._session.execute(
            f"SELECT * FROM {spec.table} WHERE {spec.pk} = ?", (self._db_pk_value(),)
        ).fetchone()

    def _exists(self) -> bool:
        return self._existing_row() is not None

    def to_sql_dict(self, *, report: "Report | None" = None, exists: bool = False) -> dict[str, Any]:
        spec = MODEL_SPECS[self.__class__.__name__]
        row: dict[str, Any] = {}
        for field_name, column_name in spec.fields.items():
            value = getattr(self, field_name, None)
            if field_name == "recorded" and value is None and report is not None and not exists:
                value = report
            if isinstance(value, DomainModel):
                value = value._pk_value()
            row[column_name] = to_db_value(value)
        return row

    def missing_required_fields(self, *, exists: bool = False) -> list[str]:
        spec = MODEL_SPECS[self.__class__.__name__]
        missing: list[str] = []
        for field_name in spec.required:
            value = getattr(self, field_name, None)
            if value is None:
                missing.append(field_name)
        # Existing placeholder refs are valid if the database row exists.
        if missing and exists and self._is_identity_only():
            return []
        return missing

    def staged_relation_objects(self) -> list["DomainModel"]:
        objects: list[DomainModel] = []
        for relation_values in self._staged_adds.values():
            objects.extend(v for v in relation_values.values() if isinstance(v, DomainModel))
        if isinstance(self, Transfer) and self.location is not None:
            objects.append(self.location)
        return objects

    def _load_relation(self, relation_name: str) -> dict[Any, "DomainModel"]:
        if relation_name in self._relation_cache:
            return self._relation_cache[relation_name]
        if self._session is None:
            self._relation_cache[relation_name] = {}
            return {}
        rel_spec = RELATION_SPECS.get(self.__class__.__name__, {}).get(relation_name)
        if rel_spec is None:
            self._relation_cache[relation_name] = {}
            return {}
        junction, owner_col, related_model_name, related_col = rel_spec
        related_cls = DOMAIN_CLASSES[related_model_name]
        related_table = MODEL_SPECS[related_model_name].table
        cursor = self._session.execute(
            f"""
            SELECT r.* FROM {related_table} r
            JOIN {junction} j ON r.{related_col} = j.{related_col}
            WHERE j.{owner_col} = ?
            """,
            (self._db_pk_value(),),
        )
        loaded = {}
        for row in cursor.fetchall():
            obj = related_cls(_session=self._session, _from_db=True, **row)
            loaded[obj._pk_value()] = obj
        self._relation_cache[relation_name] = loaded
        return loaded

    def _merged_relation(self, relation_name: str) -> list["DomainModel"]:
        merged = dict(self._load_relation(relation_name))
        for key in self._staged_removes.get(relation_name, {}):
            merged.pop(key, None)
        merged.update(self._staged_adds.get(relation_name, {}))
        return list(merged.values())

    def _stage_add(self, relation_name: str, obj: "DomainModel") -> None:
        self._ensure_mutable()
        self._staged_adds[relation_name][obj._pk_value()] = obj
        self._staged_removes[relation_name].pop(obj._pk_value(), None)
        if self._session is not None and obj._session is None:
            obj._session = self._session

    def _stage_remove(self, relation_name: str, obj: "DomainModel") -> None:
        self._ensure_mutable()
        self._staged_removes[relation_name][obj._pk_value()] = obj
        self._staged_adds[relation_name].pop(obj._pk_value(), None)

    def _relation_plan_records(self) -> list[RelationPlanRecord]:
        records: list[RelationPlanRecord] = []
        specs = RELATION_SPECS.get(self.__class__.__name__, {})
        owner_key = str(self._pk_value())
        for relation_name, relation_values in self._staged_adds.items():
            if relation_name not in specs:
                continue
            junction, _owner_col, _related_model, _related_col = specs[relation_name]
            for obj in relation_values.values():
                records.append(
                    RelationPlanRecord(
                        owner_model=self.__class__.__name__,
                        relation=relation_name,
                        table=junction,
                        action="insert",
                        owner_key=owner_key,
                        related_key=str(obj._pk_value()),
                    )
                )
        for relation_name, relation_values in self._staged_removes.items():
            if relation_name not in specs:
                continue
            junction, _owner_col, _related_model, _related_col = specs[relation_name]
            for obj in relation_values.values():
                records.append(
                    RelationPlanRecord(
                        owner_model=self.__class__.__name__,
                        relation=relation_name,
                        table=junction,
                        action="delete",
                        owner_key=owner_key,
                        related_key=str(obj._pk_value()),
                    )
                )
        if isinstance(self, Transfer) and self.location is not None:
            records.append(
                RelationPlanRecord(
                    owner_model="Transfer",
                    relation="locations",
                    table="transfer_locations",
                    action="insert",
                    owner_key=owner_key,
                    related_key=str(self.location._pk_value()),
                )
            )
        return records

    def _flush_relations(self, cursor: sqlite3.Cursor) -> None:
        specs = RELATION_SPECS.get(self.__class__.__name__, {})
        for relation_name, relation_values in self._staged_removes.items():
            if relation_name not in specs:
                continue
            junction, owner_col, _related_model_name, related_col = specs[relation_name]
            for related_obj in relation_values.values():
                cursor.execute(
                    f"DELETE FROM {junction} WHERE {owner_col} = ? AND {related_col} = ?",
                    (self._db_pk_value(), related_obj._db_pk_value()),
                )
        for relation_name, relation_values in self._staged_adds.items():
            if relation_name not in specs:
                continue
            junction, owner_col, _related_model_name, related_col = specs[relation_name]
            for related_obj in relation_values.values():
                cursor.execute(
                    f"INSERT OR IGNORE INTO {junction} ({owner_col}, {related_col}) VALUES (?, ?)",
                    (self._db_pk_value(), related_obj._db_pk_value()),
                )
        if isinstance(self, Transfer) and self.location is not None:
            cursor.execute(
                "INSERT OR IGNORE INTO transfer_locations (transfer_id, location_id) VALUES (?, ?)",
                (self._db_pk_value(), self.location._db_pk_value()),
            )
        self._staged_adds.clear()
        self._staged_removes.clear()
        self._relation_cache.clear()


class Tagable(DomainModel):
    def tags(self) -> list["Tag"]:
        return [obj for obj in self._merged_relation("tags") if isinstance(obj, Tag)]

    def add_tags(self, *tags: "Tag | str | dict[str, Any]") -> None:
        for item in tags:
            tag = self._coerce_tag(item)
            self._stage_add("tags", tag)

    def remove_tags(self, *tags: "Tag | str") -> None:
        for item in tags:
            tag = self._coerce_tag(item)
            self._stage_remove("tags", tag)

    def _coerce_tag(self, item: "Tag | str | dict[str, Any]") -> "Tag":
        if isinstance(item, Tag):
            return item
        if isinstance(item, dict):
            return Tag(_session=self._session, **item)
        if self._session is not None:
            existing = self._session.find_by_unique(Tag, "name", item)
            if existing is not None:
                return existing
        return Tag(_session=self._session, name=item)


class Commentable(DomainModel):
    def comments(self) -> list["Comment"]:
        return [obj for obj in self._merged_relation("comments") if isinstance(obj, Comment)]

    def comment(self, content: "Comment | str | dict[str, Any]") -> "Comment":
        if isinstance(content, Comment):
            comment_obj = content
        elif isinstance(content, dict):
            comment_obj = Comment(_session=self._session, **content)
        else:
            comment_obj = Comment(_session=self._session, content=content, created_at=utcnow())
        self._stage_add("comments", comment_obj)
        return comment_obj

    def remove_comment(self, comment: "Comment") -> None:
        self._stage_remove("comments", comment)


class Report(Commentable):
    id: UUID = Field(default_factory=uuid7)
    date: datetime = Field(default_factory=utcnow)
    name: Optional[str] = None
    author: Optional[str] = None
    raw_hash: Optional[bytes] = None

    def plan(self, *objects: DomainModel) -> PlanSummary:
        return self._validate_graph(objects)

    def save(self, *objects: DomainModel) -> PlanSummary:
        if self._session is None or self._session.conn is None:
            raise MissingDatabaseSessionError("Report.save() requires an open DatabaseSession")
        plan = self._validate_graph(objects)
        if not plan.is_valid:
            raise LedgerIntegrityError("; ".join(plan.errors))

        cursor = self._session.conn.cursor()
        try:
            cursor.execute("BEGIN")
            graph = self._ordered_graph(objects)
            record_by_key = {(r.model, r.key): r for r in plan.records}
            for obj in graph:
                spec = MODEL_SPECS[obj.__class__.__name__]
                record = record_by_key.get((obj.__class__.__name__, str(obj._pk_value())))
                exists = record.action != "insert" if record else obj._exists()
                if record and record.action == "unchanged":
                    obj._flush_relations(cursor)
                    continue
                row = obj.to_sql_dict(report=self, exists=exists)
                columns = list(row.keys())
                placeholders = ", ".join("?" for _ in columns)
                column_sql = ", ".join(columns)
                update_sql = ", ".join(
                    f"{col} = excluded.{col}" for col in columns if col != spec.pk
                )
                if update_sql:
                    sql = (
                        f"INSERT INTO {spec.table} ({column_sql}) VALUES ({placeholders}) "
                        f"ON CONFLICT({spec.pk}) DO UPDATE SET {update_sql}"
                    )
                else:
                    sql = (
                        f"INSERT INTO {spec.table} ({column_sql}) VALUES ({placeholders}) "
                        f"ON CONFLICT({spec.pk}) DO NOTHING"
                    )
                cursor.execute(sql, tuple(row[col] for col in columns))
                obj._loaded = True
                obj._flush_relations(cursor)
            self._session.conn.commit()
            return plan
        except sqlite3.IntegrityError as exc:
            self._session.conn.rollback()
            raise LedgerIntegrityError(str(exc)) from exc
        except Exception:
            self._session.conn.rollback()
            raise

    def _ordered_graph(self, objects: Iterable[DomainModel]) -> list[DomainModel]:
        graph = self._collect_graph(objects)
        return sorted(
            graph,
            key=lambda obj: (
                MODEL_SPECS.get(obj.__class__.__name__, MODEL_SPECS["Comment"]).dependency_order,
                obj.__class__.__name__,
                str(obj._pk_value()),
            ),
        )

    def _collect_graph(self, objects: Iterable[DomainModel]) -> list[DomainModel]:
        visited: set[tuple[type, Any]] = set()
        output: list[DomainModel] = []
        queue: list[DomainModel] = [self, *objects]
        while queue:
            obj = queue.pop(0)
            if obj is None:
                continue
            if obj._session is None:
                obj._session = self._session
            obj._register_session_identity()
            obj._propagate_session()
            key = (obj.__class__, obj._pk_value())
            if key in visited:
                continue
            visited.add(key)
            output.append(obj)

            for value in obj.__dict__.values():
                if isinstance(value, DomainModel) and value is not self:
                    queue.append(value)
            queue.extend(obj.staged_relation_objects())
        return output

    def _validate_graph(self, objects: Iterable[DomainModel]) -> PlanSummary:
        if self._session is None or self._session.conn is None:
            raise MissingDatabaseSessionError("Report.plan() requires an open DatabaseSession")
        summary = PlanSummary()
        action_counts: Counter[str] = Counter()
        update_counts: Counter[str] = Counter()
        unchanged_counts: Counter[str] = Counter()
        relation_inserts: Counter[str] = Counter()
        relation_deletes: Counter[str] = Counter()

        for obj in self._ordered_graph(objects):
            model_name = obj.__class__.__name__
            if model_name not in MODEL_SPECS:
                summary.add_error(f"Unsupported model type: {model_name}")
                continue
            spec = MODEL_SPECS[model_name]
            existing_row = obj._existing_row()
            exists = existing_row is not None
            missing = obj.missing_required_fields(exists=exists)
            if missing:
                summary.add_error(f"{model_name}({obj._pk_value()}) missing required fields: {', '.join(missing)}")
                action = "error"
            elif not exists:
                action = "insert"
                action_counts[model_name] += 1
            else:
                planned_row = obj.to_sql_dict(report=self, exists=True)
                material_change = any(
                    value is not None and existing_row.get(column) != value
                    for column, value in planned_row.items()
                    if column != spec.pk
                )
                if material_change:
                    action = "update"
                    update_counts[model_name] += 1
                else:
                    action = "unchanged"
                    unchanged_counts[model_name] += 1
            summary.records.append(
                PlanRecord(
                    model=model_name,
                    table=spec.table,
                    key=str(obj._pk_value()),
                    action=action,  # type: ignore[arg-type]
                    missing_fields=missing,
                )
            )
            for relation_record in obj._relation_plan_records():
                summary.relations.append(relation_record)
                if relation_record.action == "insert":
                    relation_inserts[relation_record.table] += 1
                else:
                    relation_deletes[relation_record.table] += 1

        summary.inserts = dict(action_counts)
        summary.updates = dict(update_counts)
        summary.unchanged = dict(unchanged_counts)
        summary.relation_inserts = dict(relation_inserts)
        summary.relation_deletes = dict(relation_deletes)
        return summary


class Asset(Tagable):
    symbol: str
    long_name: Optional[str] = None
    category: Optional[str] = None
    recorded: Optional[Report] = None


class Account(Tagable, Commentable):
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = None
    type: Optional[str] = None
    institution: Optional[str] = None
    recorded: Optional[Report] = None

    def associated(self) -> list["Entity"]:
        return [obj for obj in self._merged_relation("entities") if isinstance(obj, Entity)]

    def add_entities(self, *entities: "Entity | str | dict[str, Any]") -> None:
        for item in entities:
            if isinstance(item, Entity):
                entity = item
            elif isinstance(item, dict):
                entity = Entity(_session=self._session, **item)
            else:
                entity = Entity(_session=self._session, name=item)
            self._stage_add("entities", entity)

    def remove_entities(self, *entities: "Entity") -> None:
        for entity in entities:
            self._stage_remove("entities", entity)


class Statement(Tagable, Commentable):
    id: UUID = Field(default_factory=uuid7)
    date: Optional[datetime] = None
    account: Optional[Account] = None
    unit: Optional[Asset] = None
    balance: Optional[float] = None
    recorded: Optional[Report] = None


class Transfer(Tagable, Commentable):
    id: UUID = Field(default_factory=uuid7)
    date: Optional[datetime] = None
    sender: Optional[Account] = None
    receiver: Optional[Account] = None
    unit: Optional[Asset] = None
    amount: Optional[float] = None
    raw_hash: Optional[bytes] = None
    recorded: Optional[Report] = None
    location: Optional["Location"] = None

    def events(self) -> list["Event"]:
        return [obj for obj in self._merged_relation("events") if isinstance(obj, Event)]

    def add_involved(self, *events: "Event | str | dict[str, Any]") -> None:
        for item in events:
            if isinstance(item, Event):
                event = item
            elif isinstance(item, dict):
                event = Event(_session=self._session, **item)
            else:
                event = Event(_session=self._session, name=item, type="generic")
            self._stage_add("events", event)

    def remove_involved(self, *events: "Event") -> None:
        for event in events:
            self._stage_remove("events", event)


class Location(DomainModel):
    id: UUID = Field(default_factory=uuid7)
    city: Optional[str] = None
    state: Optional[str] = None
    category: Optional[str] = None


class Event(DomainModel):
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = None
    type: Optional[str] = None


class Entity(DomainModel):
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = None
    legal_type: Optional[str] = None


class Tag(DomainModel):
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = None
    category: Optional[str] = None
    recorded: Optional[Report] = None


class Comment(DomainModel):
    id: UUID = Field(default_factory=uuid7)
    created_at: datetime = Field(default_factory=utcnow)
    content: Optional[str] = None
    recorded: Optional[Report] = None


# Resolve forward references for Pydantic.
for _model in [Report, Asset, Account, Statement, Transfer, Location, Event, Entity, Tag, Comment]:
    _model.model_rebuild()


def clear_global_identity_map() -> None:
    """Clear objects created outside a DatabaseSession. Useful in tests."""

    GLOBAL_IDENTITY_MAP.clear()
