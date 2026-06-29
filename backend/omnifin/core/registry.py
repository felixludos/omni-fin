"""Central mapping between high-level domain objects and the SQLite schema."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ModelSpec:
    table: str
    pk: str
    identity_field: str
    fields: dict[str, str]
    dependency_order: int
    required: tuple[str, ...] = ()
    generated_pk: bool = True


MODEL_SPECS: dict[str, ModelSpec] = {
    "Report": ModelSpec(
        table="reports",
        pk="report_id",
        identity_field="id",
        fields={
            "id": "report_id",
            "date": "date",
            "name": "name",
            "author": "author",
            "raw_hash": "raw_hash",
        },
        dependency_order=0,
        required=("date",),
    ),
    "Tag": ModelSpec(
        table="tags",
        pk="tag_id",
        identity_field="id",
        fields={
            "id": "tag_id",
            "name": "name",
            "category": "category",
            "recorded": "report_id",
        },
        dependency_order=1,
        required=("name",),
    ),
    "Comment": ModelSpec(
        table="comments",
        pk="comment_id",
        identity_field="id",
        fields={
            "id": "comment_id",
            "created_at": "created_at",
            "content": "content",
            "recorded": "report_id",
        },
        dependency_order=1,
        required=("created_at", "content"),
    ),
    "Asset": ModelSpec(
        table="assets",
        pk="symbol",
        identity_field="symbol",
        fields={
            "symbol": "symbol",
            "name": "name",
            "category": "category",
            "recorded": "report_id",
        },
        dependency_order=2,
        required=("symbol",),
        generated_pk=False,
    ),
    "Investment": ModelSpec(
        table="investments",
        pk="symbol",
        identity_field="symbol",
        fields={
            "symbol": "symbol",
            "name": "name",
            "nyse_symbol": "nyse_symbol",
            "ibkr_symbol": "ibkr_symbol",
            "identifier": "identifier",
            "country": "country",
            "fund_type": "fund_type",
            "fund_focus": "fund_focus",
        },
        dependency_order=3,
        required=("symbol",),
        generated_pk=False,
    ),
    "Location": ModelSpec(
        table="locations",
        pk="location_id",
        identity_field="id",
        fields={
            "id": "location_id",
            "city": "city",
            "state": "state",
            "category": "category",
        },
        dependency_order=2,
        required=("category",),
    ),
    "Entity": ModelSpec(
        table="entities",
        pk="entity_id",
        identity_field="id",
        fields={
            "id": "entity_id",
            "name": "name",
            "legal_type": "legal_type",
        },
        dependency_order=2,
        required=("name",),
    ),
    "Account": ModelSpec(
        table="accounts",
        pk="account_id",
        identity_field="id",
        fields={
            "id": "account_id",
            "name": "name",
            "type": "type",
            "institution": "institution",
            "recorded": "report_id",
        },
        dependency_order=3,
        required=("name",),
    ),
    "Event": ModelSpec(
        table="events",
        pk="event_id",
        identity_field="id",
        fields={
            "id": "event_id",
            "name": "name",
            "type": "type",
        },
        dependency_order=3,
        required=("type",),
    ),
    "InvestmentSale": ModelSpec(
        table="investment_sales",
        pk="sale_id",
        identity_field="id",
        fields={
            "id": "sale_id",
            "acquisition_date": "acquisition_date",
            "acquisition": "acquisition_transfer_id",
            "cost_basis": "cost_basis",
            "term": "term",
        },
        dependency_order=5,
        required=("acquisition_date", "cost_basis", "term"),
    ),
    "Statement": ModelSpec(
        table="statements",
        pk="statement_id",
        identity_field="id",
        fields={
            "id": "statement_id",
            "date": "date",
            "account": "account_id",
            "unit": "asset_symbol",
            "balance": "balance",
            "recorded": "report_id",
        },
        dependency_order=4,
        required=("date", "account", "unit", "balance"),
    ),
    "Transfer": ModelSpec(
        table="transfers",
        pk="transfer_id",
        identity_field="id",
        fields={
            "id": "transfer_id",
            "date": "date",
            "sender": "sender_account_id",
            "receiver": "receiver_account_id",
            "unit": "asset_symbol",
            "amount": "amount",
            "raw_hash": "raw_hash",
            "recorded": "report_id",
        },
        dependency_order=4,
        required=("date", "sender", "receiver", "unit", "amount"),
    ),
}

SQL_PK_TO_MODEL_FIELD: dict[str, tuple[str, str]] = {
    spec.pk: (model_name, spec.identity_field) for model_name, spec in MODEL_SPECS.items()
}

# SQL column -> high-level field name per model. This lets rows from SQLite hydrate
# Pydantic objects without exposing ``account_id``/``asset_symbol`` fields.
SQL_TO_MODEL_FIELDS: dict[str, dict[str, str]] = {
    model_name: {sql_col: py_field for py_field, sql_col in spec.fields.items()}
    for model_name, spec in MODEL_SPECS.items()
}

COERCION_KEYS: dict[str, str] = {
    "Asset": "symbol",
    "Investment": "symbol",
    "Tag": "name",
    "Account": "name",
    "Report": "name",
    "Entity": "name",
    "Event": "name",
    "Location": "category",
    "Comment": "content",
}

# Junction-table metadata for staged relations. Each tuple is:
# relation name -> (junction table, owner column, related model class name, related column)
RELATION_SPECS: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "Asset": {
        "tags": ("asset_tags", "asset_symbol", "Tag", "tag_id"),
        "comments": ("asset_comments", "asset_symbol", "Comment", "comment_id"),
    },
    "Account": {
        "tags": ("account_tags", "account_id", "Tag", "tag_id"),
        "comments": ("account_comments", "account_id", "Comment", "comment_id"),
        "entities": ("entity_accounts", "account_id", "Entity", "entity_id"),
    },
    "Statement": {
        "tags": ("statement_tags", "statement_id", "Tag", "tag_id"),
        "comments": ("statement_comments", "statement_id", "Comment", "comment_id"),
    },
    "Transfer": {
        "tags": ("transfer_tags", "transfer_id", "Tag", "tag_id"),
        "comments": ("transfer_comments", "transfer_id", "Comment", "comment_id"),
        "events": ("transactions", "transfer_id", "Event", "event_id"),
        "locations": ("transfer_locations", "transfer_id", "Location", "location_id"),
    },
    "Report": {
        "comments": ("report_comments", "report_id", "Comment", "comment_id"),
    },
}

NATURAL_KEY_FIELDS: dict[str, ClassVar[tuple[str, ...]]] = {
    "Asset": ("symbol",),
    "Investment": ("symbol",),
    "Tag": ("name",),
}
