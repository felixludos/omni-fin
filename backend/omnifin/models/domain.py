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
from enum import Enum
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
    if value is None:
        return None
    if isinstance(value, (UUID, bytes, bytearray, memoryview, str)):
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
            "acquisition": "Transfer",
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


from omnifin.models.categories import AssetTagOptions, AssetType, Country, EntityType, EventType, FundType, FundEquityRatioType, SaleTerm


INVESTMENT_COMMENT_TYPES: dict[str, str] = {
    "nyse_symbol": "nyse_ticker",
    "ibkr_symbol": "ibkr_symbol",
    "identifier": "identifier",
    "country": "country",
    "fund_type": "fund_type",
    "fund_focus": "fund_focus",
}

SALE_COMMENT_TYPES: dict[str, str] = {
    "acquisition_date": "acquisition_date",
    "acquisition": "acquisition_transfer_id",
    "cost_basis": "cost_basis",
}

SALE_TERM_TAG_CATEGORY = "sale_term"
ACCOUNT_INSTITUTION_TAG_CATEGORY = "institution"
TRANSFER_SETTLED_AT_COMMENT_TYPE = "settled_at"


def _metadata_text(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _parse_datetime_text(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _comment_value(comment: "Comment") -> str | None:
    value = comment.content.strip()
    return value or None


def _first_by_type(comments: list["Comment"], comment_type: str) -> list["Comment"]:
    return [comment for comment in comments if comment.type == comment_type]


def _first_tags_by_category(tags: list["Tag"], category: str) -> list["Tag"]:
    return [tag for tag in tags if tag.category == category]


class Asset(Tagable, Commentable):
    """A fungible financial instrument or currency that can be held in an account."""
    symbol: str = Field(description="Canonical asset symbol used as primary key (e.g., USD, AAPL, VWCE).")
    name: Optional[str] = Field(default=None, description="Optional human-readable asset name.")
    category: Optional[AssetType | str] = Field(
        default=None,
        description="Normalized asset category. Prefer AssetType enum values; keep source strings only if not yet mapped.",
    )
    recorded: Optional[Report] = Field(default=None, description="Report that introduced or updated this asset.")


class Investment(Asset):
    """A financial instrument that is a security or fund, typically subject to tax reporting."""
    nyse_symbol: Optional[str] = Field(default=None, description="NYSE ticker alias if available.")
    ibkr_symbol: Optional[str] = Field(default=None, description="Interactive Brokers symbol if it differs from canonical symbol.")
    identifier: Optional[str] = Field(default=None, description="ISIN, CUSIP, WKN, or other stable instrument identifier.")
    country: Optional[Country | str] = Field(default=None, description="Primary domicile country code for the instrument.")
    fund_type: Optional[FundType | str] = Field(default=None, description="Fund structure classification used for reporting/tax logic.")
    fund_focus: Optional[FundEquityRatioType | str] = Field(
        default=None,
        description="Fund equity/real-estate exposure bucket for jurisdiction-specific tax treatment.",
    )

    @classmethod
    def db_get(cls, session: Any, key: Any) -> Optional["Investment"]:
        row = session.execute("SELECT * FROM assets WHERE symbol = ?", (to_db_value(key),)).fetchone()
        if row is None:
            return None
        investment = cls(_session=session, _from_db=True, **row)
        investment._load_investment_metadata()
        return investment if investment._has_investment_metadata() else None

    @classmethod
    def db_all(cls, session: Any, *, limit: int = 100, offset: int = 0) -> list["Investment"]:
        placeholders = ", ".join("?" for _ in INVESTMENT_COMMENT_TYPES)
        rows = session.execute(
            f"""
            SELECT DISTINCT a.*
            FROM assets a
            JOIN asset_comments ac ON ac.asset_symbol = a.symbol
            JOIN comments c ON c.comment_id = ac.comment_id
            WHERE c.type IN ({placeholders})
            ORDER BY a.symbol
            LIMIT ? OFFSET ?
            """,
            (*INVESTMENT_COMMENT_TYPES.values(), limit, offset),
        ).fetchall()
        investments = [cls(_session=session, _from_db=True, **row) for row in rows]
        for investment in investments:
            investment._load_investment_metadata()
        return investments

    @classmethod
    def db_exists(cls, session: Any, key: Any) -> bool:
        return cls.db_get(session, key) is not None

    def _has_investment_metadata(self) -> bool:
        return any(getattr(self, field_name, None) is not None for field_name in INVESTMENT_COMMENT_TYPES)

    def _load_investment_metadata(self) -> None:
        comment_map = {comment_type: _first_by_type(self.comments(), comment_type) for comment_type in INVESTMENT_COMMENT_TYPES.values()}
        for field_name, comment_type in INVESTMENT_COMMENT_TYPES.items():
            matches = comment_map.get(comment_type, [])
            if not matches:
                continue
            raw_value = _comment_value(matches[0])
            if raw_value is not None:
                object.__setattr__(self, field_name, raw_value)

    def _sync_investment_metadata(self) -> None:
        existing_comments = self.comments()
        for field_name, comment_type in INVESTMENT_COMMENT_TYPES.items():
            desired_value = getattr(self, field_name, None)
            desired_text = None if desired_value is None else _metadata_text(desired_value)
            matches = _first_by_type(existing_comments, comment_type)
            primary = matches[0] if matches else None
            for extra in matches[1:]:
                self.remove_comment(extra)
            if desired_text is None:
                if primary is not None:
                    self.remove_comment(primary)
                continue
            if primary is None:
                self.comment(Comment(_session=self._session, content=desired_text, type=comment_type, created_at=utcnow()))
                continue
            primary.content = desired_text
            primary.type = comment_type

    def _hydrate(self) -> bool:
        hydrated = super()._hydrate()
        if hydrated:
            self._load_investment_metadata()
        return hydrated

    def staged_relation_objects(self) -> list["DomainModel"]:
        self._sync_investment_metadata()
        return super().staged_relation_objects()

    def _relation_plan_records(self) -> list[RelationPlanRecord]:
        self._sync_investment_metadata()
        return super()._relation_plan_records()

    def _flush_relations(self, cursor: sqlite3.Cursor) -> None:
        self._sync_investment_metadata()
        super()._flush_relations(cursor)


class Account(Tagable, Commentable):
    """A financial account that can hold assets and record transactions."""
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = None
    type: Optional[str] = None
    institution: Optional[str] = None
    recorded: Optional[Report] = None

    def _hydrate(self) -> bool:
        hydrated = super()._hydrate()
        if hydrated:
            self._load_institution_metadata()
        return hydrated

    def _load_institution_metadata(self) -> None:
        institution_tags = _first_tags_by_category(self.tags(), ACCOUNT_INSTITUTION_TAG_CATEGORY)
        if institution_tags:
            object.__setattr__(self, "institution", institution_tags[0].name)

    def _sync_institution_metadata(self) -> None:
        existing_tags = self.tags()
        institution_tags = _first_tags_by_category(existing_tags, ACCOUNT_INSTITUTION_TAG_CATEGORY)
        primary_tag = institution_tags[0] if institution_tags else None
        for extra in institution_tags[1:]:
            self.remove_tags(extra)

        if not self.institution:
            if primary_tag is not None:
                self.remove_tags(primary_tag)
            return

        if primary_tag is None:
            self.add_tags(Tag(_session=self._session, name=self.institution, category=ACCOUNT_INSTITUTION_TAG_CATEGORY))
            return

        primary_tag.name = self.institution
        primary_tag.category = ACCOUNT_INSTITUTION_TAG_CATEGORY

    def staged_relation_objects(self) -> list["DomainModel"]:
        self._sync_institution_metadata()
        return super().staged_relation_objects()

    def _relation_plan_records(self) -> list[RelationPlanRecord]:
        self._sync_institution_metadata()
        return super()._relation_plan_records()

    def _flush_relations(self, cursor: sqlite3.Cursor) -> None:
        self._sync_institution_metadata()
        super()._flush_relations(cursor)

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
    """A financial statement that reports account balance of a specific asset at a specific date."""
    id: UUID = Field(default_factory=uuid7)
    date: Optional[datetime] = None
    account: Optional[Account] = None
    unit: Optional[Asset] = None
    balance: Optional[float] = None
    recorded: Optional[Report] = None


class Transfer(Tagable, Commentable):
    """A transfer of assets between accounts, representing a movement of value."""
    id: UUID = Field(default_factory=uuid7)
    date: Optional[datetime] = None
    sender: Optional[Account] = None
    receiver: Optional[Account] = None
    unit: Optional[Asset] = None
    amount: Optional[float] = None
    raw_hash: Optional[bytes] = None
    recorded: Optional[Report] = None
    location: Optional["Location"] = None
    settled_at: Optional[datetime] = None

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
        super().__init__(
            _session=_session,
            session=session,
            _from_db=_from_db,
            _loaded=_loaded,
            _readonly=_readonly,
            **data,
        )
        if _from_db and self._session is not None:
            self._load_transfer_metadata()

    def _hydrate(self) -> bool:
        hydrated = super()._hydrate()
        if hydrated and self._session is not None:
            self._load_transfer_metadata()
        return hydrated

    def _load_transfer_metadata(self) -> None:
        matches = _first_by_type(self.comments(), TRANSFER_SETTLED_AT_COMMENT_TYPE)
        if not matches:
            return
        raw_value = _comment_value(matches[0])
        if raw_value is None:
            return
        object.__setattr__(self, "settled_at", _parse_datetime_text(raw_value))

    def _sync_transfer_metadata(self) -> None:
        existing_comments = self.comments()
        matches = _first_by_type(existing_comments, TRANSFER_SETTLED_AT_COMMENT_TYPE)
        primary = matches[0] if matches else None
        for extra in matches[1:]:
            self.remove_comment(extra)

        if self.settled_at is None:
            if primary is not None:
                self.remove_comment(primary)
            return

        settled_text = _metadata_text(self.settled_at)
        if primary is None:
            self.comment(Comment(_session=self._session, content=settled_text, type=TRANSFER_SETTLED_AT_COMMENT_TYPE, created_at=utcnow()))
            return

        primary.content = settled_text
        primary.type = TRANSFER_SETTLED_AT_COMMENT_TYPE

    def _flush_relations(self, cursor: sqlite3.Cursor) -> None:
        self._sync_transfer_metadata()
        super()._flush_relations(cursor)

    def staged_relation_objects(self) -> list["DomainModel"]:
        self._sync_transfer_metadata()
        return super().staged_relation_objects()

    def _relation_plan_records(self) -> list[RelationPlanRecord]:
        self._sync_transfer_metadata()
        return super()._relation_plan_records()

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
    """A physical or virtual location associated with a transfer, such as a bank branch or ATM."""
    id: UUID = Field(default_factory=uuid7)
    city: Optional[str] = None
    state: Optional[str] = None
    category: Optional[Country | str] = None


class Event(Tagable, Commentable):
    """A group of transfers or other financial activities that are logically related, such as a trade or conversion."""
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = Field(default=None, description="Human-readable event label such as 'sell', 'dividend', or 'wire transfer'.")
    type: Optional[EventType | str] = Field(
        default=None,
        description="Canonical event category. Prefer EventType values and use free-form strings only when source data is more granular.",
    )

    def sale(self) -> Optional["InvestmentSale"]:
        """Return sale metadata linked to this event by shared identifier, if available."""

        if self._session is None:
            return None
        return self._session.get(InvestmentSale, self.id)


class InvestmentSale(DomainModel):
    """Additional information about a sale of an investment for tax reporting purposes."""
    id: UUID = Field(
        default_factory=uuid7,
        description="Sale identifier. Prefer sharing the same UUID as the corresponding Event.id for one-to-one linking.",
    )
    acquisition_date: Optional[datetime] = Field(
        default=None,
        description="Acquisition date of the disposed lot. Must be timezone-aware and in ISO-8601 format when serialized.",
    )
    acquisition: Optional[Transfer] = Field(
        default=None,
        description="Optional transfer that originally acquired the lot being sold.",
    )
    cost_basis: Optional[float] = Field(
        default=None,
        ge=0,
        description="Tax basis amount allocated to this disposal lot in the same monetary unit as proceeds.",
    )
    term: SaleTerm | str = Field(
        default=SaleTerm.UNKNOWN,
        description="Holding-period classification used by jurisdiction-specific tax rules.",
    )

    @classmethod
    def db_get(cls, session: Any, key: Any) -> Optional["InvestmentSale"]:
        row = session.execute("SELECT * FROM events WHERE event_id = ?", (to_db_value(key),)).fetchone()
        if row is None:
            return None
        sale = cls(_session=session, _from_db=True, id=row["event_id"])
        sale._load_sale_metadata()
        return sale if sale._has_sale_metadata() else None

    @classmethod
    def db_all(cls, session: Any, *, limit: int = 100, offset: int = 0) -> list["InvestmentSale"]:
        placeholders = ", ".join("?" for _ in SALE_COMMENT_TYPES)
        rows = session.execute(
            f"""
            SELECT DISTINCT e.event_id
            FROM events e
            LEFT JOIN event_comments ec ON ec.event_id = e.event_id
            LEFT JOIN comments c ON c.comment_id = ec.comment_id
            LEFT JOIN event_tags et ON et.event_id = e.event_id
            LEFT JOIN tags t ON t.tag_id = et.tag_id
            WHERE c.type IN ({placeholders}) OR t.category = ?
            ORDER BY e.event_id
            LIMIT ? OFFSET ?
            """,
            (*SALE_COMMENT_TYPES.values(), SALE_TERM_TAG_CATEGORY, limit, offset),
        ).fetchall()
        sales: list[InvestmentSale] = []
        for row in rows:
            sale = cls.db_get(session, row["event_id"])
            if sale is not None:
                sales.append(sale)
        return sales

    @classmethod
    def db_exists(cls, session: Any, key: Any) -> bool:
        return cls.db_get(session, key) is not None

    def _has_sale_metadata(self) -> bool:
        return any(getattr(self, field_name, None) is not None for field_name in SALE_COMMENT_TYPES) or self.term not in (None, SaleTerm.UNKNOWN, SaleTerm.UNKNOWN.value)

    def _load_sale_metadata(self) -> None:
        event = self._session.get(Event, self.id) if self._session is not None else None
        if event is None:
            return
        for field_name, comment_type in SALE_COMMENT_TYPES.items():
            matches = _first_by_type(event.comments(), comment_type)
            if not matches:
                continue
            raw_value = _comment_value(matches[0])
            if raw_value is None:
                continue
            if field_name == "acquisition_date":
                object.__setattr__(self, field_name, _parse_datetime_text(raw_value))
            elif field_name == "cost_basis":
                object.__setattr__(self, field_name, float(raw_value))
            elif field_name == "acquisition":
                object.__setattr__(self, field_name, Transfer(id=parse_uuid(raw_value), _session=self._session))
        term_tags = _first_tags_by_category(event.tags(), SALE_TERM_TAG_CATEGORY)
        if term_tags:
            object.__setattr__(self, "term", term_tags[0].name)

    def to_sql_dict(self, *, report: "Report | None" = None, exists: bool = False) -> dict[str, Any]:
        return {"event_id": to_db_value(self.id), "type": EventType.TRADE.value}

    def _existing_row(self) -> dict[str, Any] | None:
        if self._session is None:
            return None
        return self._session.execute(
            "SELECT * FROM events WHERE event_id = ?",
            (self._db_pk_value(),),
        ).fetchone()

    def _hydrate(self) -> bool:
        if self._session is None or self._loaded or self._hydrating:
            return self._loaded
        self._hydrating = True
        try:
            row = self._existing_row()
            if row is None:
                self._loaded = True
                return False
            self._load_sale_metadata()
            self._loaded = True
            return True
        finally:
            self._hydrating = False

    def _sync_sale_metadata(self) -> None:
        if self._session is None:
            return
        event = self._session.get(Event, self.id)
        if event is None:
            event = Event(_session=self._session, id=self.id, type=EventType.TRADE.value)
        elif event.type is None:
            event.type = EventType.TRADE.value

        existing_comments = event.comments()
        for field_name, comment_type in SALE_COMMENT_TYPES.items():
            desired_value = getattr(self, field_name, None)
            desired_text = None if desired_value is None else _metadata_text(desired_value._pk_value() if isinstance(desired_value, DomainModel) else desired_value)
            matches = _first_by_type(existing_comments, comment_type)
            primary = matches[0] if matches else None
            for extra in matches[1:]:
                event.remove_comment(extra)
            if desired_text is None:
                if primary is not None:
                    event.remove_comment(primary)
                continue
            if primary is None:
                event.comment(Comment(_session=self._session, content=desired_text, type=comment_type, created_at=utcnow()))
                continue
            primary.content = desired_text
            primary.type = comment_type

        desired_term = None if self.term is None else _metadata_text(self.term)
        term_tags = _first_tags_by_category(event.tags(), SALE_TERM_TAG_CATEGORY)
        primary_tag = term_tags[0] if term_tags else None
        for extra in term_tags[1:]:
            event.remove_tags(extra)
        if desired_term is None:
            if primary_tag is not None:
                event.remove_tags(primary_tag)
        elif primary_tag is None:
            event.add_tags(Tag(_session=self._session, name=desired_term, category=SALE_TERM_TAG_CATEGORY))
        else:
            primary_tag.name = desired_term
            primary_tag.category = SALE_TERM_TAG_CATEGORY

    def _relation_plan_records(self) -> list[RelationPlanRecord]:
        self._sync_sale_metadata()
        return super()._relation_plan_records()

    def _flush_relations(self, cursor: sqlite3.Cursor) -> None:
        self._sync_sale_metadata()
        event = self._session.get(Event, self.id) if self._session is not None else None
        if event is not None:
            event._flush_relations(cursor)

    def staged_relation_objects(self) -> list["DomainModel"]:
        self._sync_sale_metadata()
        objects = super().staged_relation_objects()
        if self._session is None:
            return objects
        event = self._session.get(Event, self.id)
        if event is None:
            return objects
        return [event, *event.staged_relation_objects(), *objects]


class Entity(DomainModel):
    """A legal or organizational entity that can hold assets or engage in financial transactions."""
    id: UUID = Field(default_factory=uuid7)
    name: Optional[str] = None
    legal_type: Optional[EntityType | str] = None


class Tag(DomainModel):
    """A label or category that can be applied to financial records for organization or reporting purposes."""
    id: UUID = Field(default_factory=uuid7)
    name: str = None
    category: Optional[str] = None
    recorded: Optional[Report] = None


class AssetTag(Tag):
    category: Optional[AssetTagOptions | str] = None


class Comment(DomainModel):
    """A user-provided note or annotation associated with a financial record."""
    id: UUID = Field(default_factory=uuid7)
    created_at: datetime = Field(default_factory=utcnow)
    content: str = None
    type: Optional[str] = None
    recorded: Optional[Report] = None


# Resolve forward references for Pydantic.
for _model in [Report, Asset, Investment, Account, Statement, Transfer, Location, Event, InvestmentSale, Entity, Tag, Comment]:
    _model.model_rebuild()


def clear_global_identity_map() -> None:
    """Clear objects created outside a DatabaseSession. Useful in tests."""

    GLOBAL_IDENTITY_MAP.clear()
