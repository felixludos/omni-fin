


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
    asset_class TEXT      -- 'fiat', 'equity', 'crypto', 'bond', 'etf'
) STRICT;


CREATE TABLE accounts (
    account_id BLOB PRIMARY KEY, -- UUIDv7 of the account
    
	name TEXT NOT NULL,
    
	type TEXT,            -- 'internal', 'external', 'merchant'
    institution TEXT,
	recorded_with BLOB,        -- UUIDv7 of report when this account was inserted
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
) STRICT;


CREATE TABLE statements (
    statement_id BLOB PRIMARY KEY,
    date TEXT NOT NULL,        -- ISO8601 string
    
	account_id BLOB NOT NULL,
    asset_symbol TEXT NOT NULL,    -- Track balance per asset (e.g., cash balance vs stock balance)
    balance REAL NOT NULL,
	
	recorded_with BLOB,        -- UUIDv7 of report when this statement was inserted
    FOREIGN KEY(account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(asset_symbol) REFERENCES assets(symbol),
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
) STRICT;


CREATE TABLE transfers (
    transfer_id BLOB PRIMARY KEY,
    date TEXT NOT NULL,        -- ISO8601 string
	
	sender_account_id BLOB NOT NULL,
	receiver_account_id BLOB NOT NULL,
    asset_symbol TEXT NOT NULL,    -- References assets(symbol)
    amount REAL NOT NULL,        -- Always positive
	
	raw_hash BLOB,          -- Hash of the original source data (e.g., CSV row)
	recorded_with BLOB,        -- UUIDv7 of report when this transfer was inserted
    FOREIGN KEY(asset_symbol) REFERENCES assets(symbol),
    FOREIGN KEY(sender_account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(receiver_account_id) REFERENCES accounts(account_id),
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
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
	recorded_with BLOB,        -- UUIDv7 of report when this tag was inserted
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
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


CREATE TABLE transfer_comments (
	comment_id BLOB PRIMARY KEY,
	transfer_id BLOB NOT NULL REFERENCES transfers(transfer_id) ON DELETE CASCADE,
	created_at TEXT NOT NULL, -- ISO8601 string
	
	content TEXT NOT NULL,

	updates_id BLOB,        -- UUIDv7 of report when this comment was inserted
	recorded_with BLOB,        -- UUIDv7 of report when this comment was inserted
	FOREIGN KEY(updates_id) REFERENCES report_comments(comment_id),
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
) STRICT;

CREATE TABLE statement_comments (
	comment_id BLOB PRIMARY KEY,
	statement_id BLOB NOT NULL REFERENCES statements(statement_id) ON DELETE CASCADE,
	created_at TEXT NOT NULL, -- ISO8601 string
	
	content TEXT NOT NULL,

	updates_id BLOB,        -- UUIDv7 of report when this comment was inserted
	recorded_with BLOB,        -- UUIDv7 of report when this comment was inserted
	FOREIGN KEY(updates_id) REFERENCES report_comments(comment_id),
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
) STRICT;

CREATE TABLE report_comments (
	comment_id BLOB PRIMARY KEY,
	report_id BLOB NOT NULL REFERENCES report(report_id) ON DELETE CASCADE,
	created_at TEXT NOT NULL, -- ISO8601 string
	
	content TEXT NOT NULL,

	updates_id BLOB,        -- UUIDv7 of report when this comment was inserted
	recorded_with BLOB,        -- UUIDv7 of report when this comment was inserted
	FOREIGN KEY(updates_id) REFERENCES report_comments(comment_id),
	FOREIGN KEY(recorded_with) REFERENCES report(report_id)
) STRICT;

```

high level types

```python

import uuid6
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator, PrivateAttr
from typing import Any, Dict, Iterable
import sqlite3


class Tagable(BaseModel):
	def tags(self) -> Iterable["Tag"]:
		raise NotImplementedError("This method should be implemented to return associated tags.")

	def add_tags(self, *tags: "Tag" | str) -> None:
		raise NotImplementedError("This method should be implemented to add tags.")

	def remove_tags(self, *tags: "Tag") -> None:
		raise NotImplementedError("This method should be implemented to remove tags.")


class Commentable(BaseModel):
	def comments(self) -> Iterable["Comment"]:
		raise NotImplementedError("This method should be implemented to return associated comments.")

	def comment(self, content: "Comment" | str) -> None:
		raise NotImplementedError("This method should be implemented to add a comment.")

	def remove_comment(self, comment: "Comment") -> None:
		raise NotImplementedError("This method should be implemented to remove a comment.")


class Report(Commentable):
	id: UUID
	date: datetime
	name: Optional[str] = None
	author: Optional[str] = None
	raw_hash: Optional[bytes] = None

class Asset(Tagable):
	symbol: str
	long_name: Optional[str] = None
	category: Optional[str] = None

class Account(Tagable):
	id: UUID
	name: str
	type: Optional[str] = None
	institution: Optional[str] = None
	recorded: Optional[Report] = None # lazy

	def associated(self) -> Iterable["Entity"]:
		raise NotImplementedError("This method should be implemented to return associated entities.")

	def add_owners(self, *owners: "Entity" | str) -> None:
		raise NotImplementedError("This method should be implemented to add associated entities.")
	
	def remove_owners(self, *owners: "Entity") -> None:
		raise NotImplementedError("This method should be implemented to remove associated entities.")


class Statement(Tagable, Commentable):
	id: UUID
	date: datetime
	account: Account # lazy
	unit: Asset # lazy
	balance: float
	recorded: Optional[Report] = None # lazy


class Transfer(Tagable, Commentable):
	id: UUID
	date: datetime
	sender: Account # lazy
	receiver: Account # lazy
	unit: Asset # lazy
	amount: float
	raw_hash: Optional[bytes] = None
	recorded: Optional[Report] = None # lazy

	location: Optional[Location] = None # lazy
	
	def events(self) -> Iterable["Event"]: # cached
		raise NotImplementedError("This method should be implemented to return associated events.")

	def add_involved(self, *events: "Event" | str) -> None:
		raise NotImplementedError("This method should be implemented to add associated events.")

	def remove_involved(self, *events: "Event") -> None:
		raise NotImplementedError("This method should be implemented to remove associated events.")


class Location(BaseModel):
	id: UUID
	city: Optional[str] = None
	state: Optional[str] = None
	category: str

class Event(BaseModel):
	id: UUID
	name: Optional[str] = None
	type: str

class Entity(BaseModel):
	id: UUID
	name: str
	legal_type: Optional[str] = None

class Tag(BaseModel):
	id: UUID
	name: str
	category: Optional[str] = None
	recorded: Optional[Report] = None # lazy

class Comment(BaseModel):
	id: UUID
	created_at: datetime
	content: str
	recorded: Optional[Report] = None # lazy

```