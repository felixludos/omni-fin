

here's an updated. note the matches are basically just booleans, since the matches themselves don't need to be stored as they are redundant. a report is meant to signify

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
    name TEXT NOT NULL,
    asset_class TEXT NOT NULL,      -- 'fiat', 'equity', 'crypto', 'bond', 'etf'
	report_id BLOB,        -- UUIDv7 of report when this asset was inserted
	FOREIGN KEY(report_id) REFERENCES report(report_id)
) STRICT;


CREATE TABLE accounts (
    account_id BLOB PRIMARY KEY, -- UUIDv7 of the account
    name TEXT NOT NULL,
    type TEXT NOT NULL,            -- 'internal', 'external', 'merchant'
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
	location TEXT NOT NULL,    -- "City, State/Country" or "Country"
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
	settled_at TEXT NOT NULL, -- ISO8601 string
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
	content TEXT NOT NULL,
	created_at TEXT NOT NULL, -- ISO8601 string
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
