


```sql
PRAGMA foreign_keys = ON;


CREATE TABLE report (
    report_id BLOB PRIMARY KEY, -- UUIDv7 of the report
    date TEXT NOT NULL,        -- ISO8601 string
    name TEXT, -- defaults to the name of the csv file or the report source
	author TEXT,
    raw_hash BLOB          -- Hash of the original source data (e.g., CSV file)
) STRICT;


CREATE TABLE assets (
    symbol TEXT PRIMARY KEY,       -- 'USD', 'EUR', 'AAPL', 'BTC' (must be unique)
    
	long_name TEXT,
    asset_class TEXT,      -- 'fiat', 'equity', 'crypto', 'bond', 'etf'
	report_id BLOB,        -- UUIDv7 of report when this asset was inserted
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;


CREATE TABLE accounts (
    account_id BLOB PRIMARY KEY, -- UUIDv7 of the account
    
	name TEXT NOT NULL,
    
	type TEXT,            -- 'internal', 'external', 'merchant'
    institution TEXT,
	report_id BLOB,        -- UUIDv7 of report when this account was inserted
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;


CREATE TABLE statements (
    statement_id BLOB PRIMARY KEY,
    date TEXT NOT NULL,        -- ISO8601 string
    
	account_id BLOB NOT NULL,
    asset_symbol TEXT NOT NULL,    -- Track balance per asset (e.g., cash balance vs stock balance)
    balance REAL NOT NULL,
	
	report_id BLOB,        -- UUIDv7 of report when this statement was inserted
    FOREIGN KEY(account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(asset_symbol) REFERENCES assets(symbol),
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;


CREATE TABLE transfers (
    transfer_id BLOB PRIMARY KEY,
    date TEXT NOT NULL,        -- ISO8601 string
	
	sender_account_id BLOB NOT NULL,
	receiver_account_id BLOB NOT NULL,
    asset_symbol TEXT NOT NULL,    -- References assets(symbol)
    amount REAL NOT NULL,        -- Always positive
	
	raw_hash BLOB,          -- Hash of the original source data (e.g., CSV row)
	report_id BLOB,        -- UUIDv7 of report when this transfer was inserted
    FOREIGN KEY(asset_symbol) REFERENCES assets(symbol),
    FOREIGN KEY(sender_account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(receiver_account_id) REFERENCES accounts(account_id),
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;

CREATE TABLE transfer_matches (
    source_transfer_id BLOB NOT NULL,
	receiver_transfer_id BLOB NOT NULL,
    FOREIGN KEY(source_transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
	FOREIGN KEY(receiver_transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
	PRIMARY KEY (source_transfer_id, receiver_transfer_id)
) STRICT;

CREATE TABLE transfer_times ( -- details of when a transfer was initiated and settled
	transfer_id BLOB PRIMARY KEY,
	initiated_at TEXT, -- ISO8601 string
	settled_at TEXT, -- ISO8601 string
	FOREIGN KEY(transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE
) STRICT;


CREATE TABLE locations ( -- details of where a transfer occurred
	location_id BLOB PRIMARY KEY,
	city TEXT, -- optional
	state TEXT, -- optional
	category TEXT NOT NULL, -- ISO 3166-1 alpha-2 country code or "online"
) STRICT;

CREATE TABLE transfer_locations (
	transfer_id BLOB NOT NULL REFERENCES transfers(transfer_id) ON DELETE CASCADE,
	location_id BLOB NOT NULL REFERENCES locations(location_id) ON DELETE CASCADE,
	PRIMARY KEY (transfer_id, location_id)
) STRICT;


CREATE TABLE events ( -- for projects or any event that involves multiple transfers (such as a group of taxable events for 2026, or trades or conversions)
    event_id BLOB PRIMARY KEY,
	
    name TEXT,

	type TEXT NOT NULL
) STRICT;

CREATE TABLE transactions (
	transfer_id BLOB NOT NULL REFERENCES transfers(transfer_id) ON DELETE CASCADE,
	event_id BLOB NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
	PRIMARY KEY (transfer_id, event_id)
) STRICT;


CREATE TABLE entities (
    entity_id BLOB PRIMARY KEY,

    name TEXT NOT NULL,

    legal_type TEXT -- e.g., 'individual', 'joint', 'conservatorship', 'corporate'
) STRICT;

CREATE TABLE entity_accounts (
	entity_id BLOB NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
	account_id BLOB NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
	PRIMARY KEY (entity_id, account_id)
) STRICT;


CREATE TABLE tags (
    tag_id BLOB PRIMARY KEY,

    name TEXT UNIQUE NOT NULL,

	category TEXT,
	report_id BLOB,        -- UUIDv7 of report when this tag was inserted
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;

CREATE TABLE asset_tags (
    asset_symbol TEXT NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    tag_id BLOB NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (asset_symbol, tag_id)
) STRICT;

CREATE TABLE accounts_tags (
    account_id BLOB NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, tag_id)
) STRICT;

CREATE TABLE transfers_tags (
    transfer_id BLOB NOT NULL REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (transfer_id, tag_id)
) STRICT;

CREATE TABLE statements_tags (
	statement_id BLOB NOT NULL REFERENCES statements(statement_id) ON DELETE CASCADE,
	tag_id BLOB NOT NULL REFERENCES tags(tag_id) ON DELETE CASCADE,
	PRIMARY KEY (statement_id, tag_id)
) STRICT;


CREATE TABLE comments (
	comment_id BLOB PRIMARY KEY,
	created_at TEXT NOT NULL, -- ISO8601 string

	content TEXT NOT NULL,
	
	report_id BLOB,        -- UUIDv7 of report when this comment was inserted
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;

CREATE TABLE asset_comments (
	asset_symbol TEXT NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
	comment_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	PRIMARY KEY (asset_symbol, comment_id)
) STRICT;

CREATE TABLE account_comments (
	account_id BLOB NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
	comment_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	PRIMARY KEY (account_id, comment_id)
) STRICT;

CREATE TABLE transfer_comments (
	transfer_id BLOB NOT NULL REFERENCES transfers(transfer_id) ON DELETE CASCADE,
	comment_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	PRIMARY KEY (transfer_id, comment_id)
) STRICT;

CREATE TABLE statement_comments (
	statement_id BLOB NOT NULL REFERENCES statements(statement_id) ON DELETE CASCADE,
	comment_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	PRIMARY KEY (statement_id, comment_id)
) STRICT;

CREATE TABLE report_comments (
	report_id BLOB NOT NULL REFERENCES report(report_id) ON DELETE CASCADE,
	comment_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	PRIMARY KEY (report_id, comment_id)
) STRICT;

CREATE TABLE comment_updates (
	original_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	update_id BLOB NOT NULL REFERENCES comments(comment_id) ON DELETE CASCADE,
	PRIMARY KEY (original_id, update_id)
) STRICT;

```

high level types

```python

from pydantic import BaseModel, Field
from typing import List, Dict, Any
from collections import defaultdict

class PlanSummary(BaseModel):
    is_valid: bool
    missing_dependencies: List[str] = Field(default_factory=list)
    inserts: Dict[str, int] = Field(default_factory=lambda: defaultdict(int))
    updates: Dict[str, int] = Field(default_factory=lambda: defaultdict(int))
    
    def display(self):
        """Helper to print the plan to the CLI."""
        print(f"Plan Valid: {self.is_valid}")
        if not self.is_valid:
            print("Errors:")
            for err in self.missing_dependencies:
                print(f" - {err}")
        print("\nTo Insert:", dict(self.inserts))
        print("To Update:", dict(self.updates))

#######################

# Map Pydantic Model classes to (Table Name, Primary Key Column)
TABLE_REGISTRY = {
    "Asset": ("assets", "symbol"),
    "Account": ("accounts", "account_id"),
    "Transfer": ("transfers", "transfer_id"),
    "Tag": ("tags", "tag_id"),
    "TransferTag": ("transfers_tags", "transfer_id") # Note: Composite keys need special handling if updated, but junction tables are usually purely inserts/deletes.
}

####################

import sqlite3
from uuid import UUID

class Report(DomainModel):
    report_id: UUID
    date: str
    name: str | None = None
    author: str | None = None
    raw_hash: bytes | None = None

    def plan(self, *objects: DomainModel) -> PlanSummary:
        """
        Evaluates objects against the current DB state.
        Determines what is new vs updated, and checks FK constraints.
        """
        summary = PlanSummary(is_valid=True)
        cursor = self._db.cursor()
        
        # Track IDs being created in this session to satisfy FK checks locally
        staged_ids = {
            getattr(obj, TABLE_REGISTRY[obj.__class__.__name__][1]) 
            for obj in objects if obj.__class__.__name__ in TABLE_REGISTRY
        }

        for obj in objects:
            cls_name = obj.__class__.__name__
            if cls_name not in TABLE_REGISTRY:
                summary.is_valid = False
                summary.missing_dependencies.append(f"Unknown model type: {cls_name}")
                continue

            table_name, pk_col = TABLE_REGISTRY[cls_name]
            obj_data = obj.model_dump(exclude_unset=True)
            pk_val = obj_data.get(pk_col)

            # Convert UUIDs to bytes for SQLite lookup
            lookup_val = pk_val.bytes if isinstance(pk_val, UUID) else pk_val

            # 1. Check if it's an Insert or Update
            cursor.execute(f"SELECT 1 FROM {table_name} WHERE {pk_col} = ?", (lookup_val,))
            if cursor.fetchone():
                summary.updates[cls_name] += 1
            else:
                summary.inserts[cls_name] += 1

            # 2. Dependency Validation (Example: Transfer must have valid accounts)
            if cls_name == "Transfer":
                for fk_col in ["sender_account_id", "receiver_account_id"]:
                    fk_val = obj_data.get(fk_col)
                    if fk_val not in staged_ids:
                        # If not in staging, it MUST exist in the DB
                        cursor.execute("SELECT 1 FROM accounts WHERE account_id = ?", (fk_val.bytes,))
                        if not cursor.fetchone():
                            summary.is_valid = False
                            summary.missing_dependencies.append(
                                f"Transfer {pk_val} references missing {fk_col}: {fk_val}"
                            )

        return summary

    def save(self, *objects: DomainModel):
        """
        Executes the plan. Injects the report_id and executes an Upsert transaction.
        """
        # 1. Run the plan to validate
        summary = self.plan(*objects)
        if not summary.is_valid:
            raise ValueError(f"Cannot save report. Dependencies missing: {summary.missing_dependencies}")

        cursor = self._db.cursor()

        try:
            # 2. Begin atomic transaction
            cursor.execute("BEGIN TRANSACTION;")

            for obj in objects:
                cls_name = obj.__class__.__name__
                table_name, pk_col = TABLE_REGISTRY[cls_name]
                
                # Assign this report_id to the object if it has that field
                if hasattr(obj, 'report_id'):
                    obj.report_id = self.report_id

                # Serialize Pydantic model to dict, converting UUIDs to bytes for SQLite
                data = {}
                for key, val in obj.model_dump().items():
                    if isinstance(val, UUID):
                        data[key] = val.bytes
                    else:
                        data[key] = val

                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                
                # Dynamic Upsert (SQLite >= 3.24)
                # If the PK exists, update the other fields. If not, insert.
                set_clause = ", ".join([f"{col}=excluded.{col}" for col in data.keys() if col != pk_col])
                
                sql = f"""
                    INSERT INTO {table_name} ({columns}) 
                    VALUES ({placeholders})
                    ON CONFLICT({pk_col}) DO UPDATE SET {set_clause};
                """
                
                cursor.execute(sql, tuple(data.values()))

            # 3. Commit transaction
            self._db.commit()

        except Exception as e:
            self._db.rollback()
            raise RuntimeError(f"Database save failed, transaction rolled back. Error: {e}")

##################

# 1. Parse your CSV into Python objects
new_fidelity_account = Account(account_id=uuid6.uuid7(), name="Fidelity Taxable", type="internal")
new_transfer = Transfer(
    transfer_id=uuid6.uuid7(), 
    date="2026-07-01", 
    sender_account_id=new_fidelity_account.account_id,
    # ... other fields
)

# 2. Create the Report Unit of Work
report = Report(db=db_connection, report_id=uuid6.uuid7(), name="July 2026 Import")

# 3. Plan the execution (Outputs a PlanSummary Pydantic object)
plan = report.plan(new_fidelity_account, new_transfer)
plan.display() 
# To Insert: {'Account': 1, 'Transfer': 1}
# To Update: {}

# 4. Execute atomic save
if plan.is_valid:
    report.save(new_fidelity_account, new_transfer)



#################






```

```python

import uuid6
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, PrivateAttr
from typing import Any, Dict
import sqlite3

# Unified registry mapping class names to their SQL table and PK column
TABLE_REGISTRY = {
    "Report": {"table": "report", "pk": "report_id"},
    "Account": {"table": "accounts", "pk": "account_id"},
    "Transfer": {"table": "transfers", "pk": "transfer_id"},
    "Statement": {"table": "statements", "pk": "statement_id"},
    "Asset": {"table": "assets", "pk": "symbol"}, # Exception: uses string ticker
}

class DomainModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)
    
    # Auto-generates a UUIDv7 on creation. (Ignored for Assets which use string symbols).
    id: UUID | str = Field(default_factory=uuid6.uuid7)
    
    _db: sqlite3.Connection | None = PrivateAttr(default=None)

    def __init__(self, db: sqlite3.Connection = None, **data):
        super().__init__(**data)
        if db:
            self._db = db

    @model_validator(mode='before')
    @classmethod
    def map_sql_pk_to_id(cls, data: Any) -> Any:
        """When reading from SQLite, map the specific PK column (e.g., 'account_id') to 'id'."""
        if isinstance(data, dict):
            registry_entry = TABLE_REGISTRY.get(cls.__name__)
            if registry_entry:
                pk_col = registry_entry["pk"]
                if pk_col in data:
                    data["id"] = data.pop(pk_col)
        return data

    def to_sql_dict(self) -> Dict[str, Any]:
        """When writing to SQLite, map 'id' back to the specific PK column and convert UUIDs to bytes."""
        data = self.model_dump(exclude_unset=True)
        registry_entry = TABLE_REGISTRY.get(self.__class__.__name__)
        
        if registry_entry:
            pk_col = registry_entry["pk"]
            pk_val = data.pop("id")
            # Only convert to bytes if it's a UUID (leaves Asset symbols as strings)
            data[pk_col] = pk_val.bytes if isinstance(pk_val, UUID) else pk_val

        # Convert any remaining UUID foreign keys (like sender_account_id) to bytes
        for key, val in data.items():
            if isinstance(val, UUID):
                data[key] = val.bytes
                
        return data


from typing import Optional
from datetime import datetime

class Account(DomainModel):
    name: str
    type: str
    institution: Optional[str] = None
    report_id: Optional[UUID] = None

class Transfer(DomainModel):
    date: datetime
    sender_account_id: UUID
    receiver_account_id: UUID
    asset_symbol: str
    amount: float
    raw_hash: Optional[bytes] = None
    report_id: Optional[UUID] = None

class Asset(DomainModel):
    # Overrides the default UUID generation to use the ticker symbol directly as the ID
    id: str 
    name: str
    asset_class: str
    report_id: Optional[UUID] = None


```