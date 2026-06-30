PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;

CREATE TABLE IF NOT EXISTS reports (
    report_id BLOB PRIMARY KEY CHECK(length(report_id) = 16),
    date TEXT NOT NULL,
    name TEXT,
    author TEXT,
    raw_hash BLOB
) STRICT;

CREATE TABLE IF NOT EXISTS assets (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    category TEXT,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

CREATE TABLE IF NOT EXISTS accounts (
    account_id BLOB PRIMARY KEY CHECK(length(account_id) = 16),
    name TEXT NOT NULL,
    type TEXT CHECK(type IS NULL OR type IN ('internal', 'external', 'merchant', 'brokerage', 'bank', 'tax_authority')),
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

CREATE TABLE IF NOT EXISTS statements (
    statement_id BLOB PRIMARY KEY CHECK(length(statement_id) = 16),
    date TEXT NOT NULL,
    account_id BLOB NOT NULL CHECK(length(account_id) = 16),
    asset_symbol TEXT NOT NULL,
    balance REAL NOT NULL,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(asset_symbol) REFERENCES assets(symbol),
    FOREIGN KEY(report_id) REFERENCES reports(report_id),
    UNIQUE(account_id, asset_symbol, date)
) STRICT;

CREATE TABLE IF NOT EXISTS transfers (
    transfer_id BLOB PRIMARY KEY CHECK(length(transfer_id) = 16),
    date TEXT NOT NULL,
    sender_account_id BLOB NOT NULL CHECK(length(sender_account_id) = 16),
    receiver_account_id BLOB NOT NULL CHECK(length(receiver_account_id) = 16),
    asset_symbol TEXT NOT NULL,
    amount REAL NOT NULL CHECK(amount > 0),
    raw_hash BLOB,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(asset_symbol) REFERENCES assets(symbol),
    FOREIGN KEY(sender_account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(receiver_account_id) REFERENCES accounts(account_id),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

CREATE TABLE IF NOT EXISTS transfer_matches (
    source_transfer_id BLOB NOT NULL CHECK(length(source_transfer_id) = 16),
    receiver_transfer_id BLOB NOT NULL CHECK(length(receiver_transfer_id) = 16),
    FOREIGN KEY(source_transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    PRIMARY KEY (source_transfer_id, receiver_transfer_id),
    CHECK(source_transfer_id != receiver_transfer_id)
) STRICT;

CREATE TABLE IF NOT EXISTS locations (
    location_id BLOB PRIMARY KEY CHECK(length(location_id) = 16),
    city TEXT,
    state TEXT,
    country TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS transfer_locations (
    transfer_id BLOB NOT NULL CHECK(length(transfer_id) = 16) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    location_id BLOB NOT NULL CHECK(length(location_id) = 16) REFERENCES locations(location_id) ON DELETE CASCADE,
    PRIMARY KEY (transfer_id, location_id)
) STRICT;

CREATE TABLE IF NOT EXISTS events (
    event_id BLOB PRIMARY KEY CHECK(length(event_id) = 16),
    name TEXT,
    type TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS transactions (
    transfer_id BLOB NOT NULL CHECK(length(transfer_id) = 16) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    event_id BLOB NOT NULL CHECK(length(event_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    association TEXT,
    PRIMARY KEY (transfer_id, event_id)
) STRICT;

CREATE TABLE IF NOT EXISTS event_links (
    event_1_id BLOB NOT NULL CHECK(length(event_1_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    event_2_id BLOB NOT NULL CHECK(length(event_2_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    link_type TEXT,
    PRIMARY KEY (event_1_id, event_2_id),
    CHECK(event_1_id != event_2_id)
) STRICT;


CREATE TABLE IF NOT EXISTS entities (
    entity_id BLOB PRIMARY KEY CHECK(length(entity_id) = 16),
    name TEXT NOT NULL,
    legal_type TEXT
) STRICT;

CREATE TABLE IF NOT EXISTS entity_accounts (
    entity_id BLOB NOT NULL CHECK(length(entity_id) = 16) REFERENCES entities(entity_id) ON DELETE CASCADE,
    account_id BLOB NOT NULL CHECK(length(account_id) = 16) REFERENCES accounts(account_id) ON DELETE CASCADE,
    relationship TEXT,
    PRIMARY KEY (entity_id, account_id)
) STRICT;

CREATE TABLE IF NOT EXISTS tags (
    tag_id BLOB PRIMARY KEY CHECK(length(tag_id) = 16),
    name TEXT NOT NULL,
    category TEXT,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

CREATE TABLE IF NOT EXISTS asset_tags (
    asset_symbol TEXT NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (asset_symbol, tag_id)
) STRICT;

CREATE TABLE IF NOT EXISTS account_tags (
    account_id BLOB NOT NULL CHECK(length(account_id) = 16) REFERENCES accounts(account_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, tag_id)
) STRICT;

CREATE TABLE IF NOT EXISTS transfer_tags (
    transfer_id BLOB NOT NULL CHECK(length(transfer_id) = 16) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (transfer_id, tag_id)
) STRICT;

CREATE TABLE IF NOT EXISTS statement_tags (
    statement_id BLOB NOT NULL CHECK(length(statement_id) = 16) REFERENCES statements(statement_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (statement_id, tag_id)
) STRICT;

CREATE TABLE IF NOT EXISTS event_tags (
    event_id BLOB NOT NULL CHECK(length(event_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, tag_id)
) STRICT;

CREATE TABLE IF NOT EXISTS comments (
    comment_id BLOB PRIMARY KEY CHECK(length(comment_id) = 16),
    content TEXT NOT NULL,
    type TEXT,
    created_at TEXT NOT NULL,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

CREATE TABLE IF NOT EXISTS asset_comments (
    asset_symbol TEXT NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (asset_symbol, comment_id)
) STRICT;

CREATE TABLE IF NOT EXISTS account_comments (
    account_id BLOB NOT NULL CHECK(length(account_id) = 16) REFERENCES accounts(account_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, comment_id)
) STRICT;

CREATE TABLE IF NOT EXISTS transfer_comments (
    transfer_id BLOB NOT NULL CHECK(length(transfer_id) = 16) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (transfer_id, comment_id)
) STRICT;

CREATE TABLE IF NOT EXISTS statement_comments (
    statement_id BLOB NOT NULL CHECK(length(statement_id) = 16) REFERENCES statements(statement_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (statement_id, comment_id)
) STRICT;

CREATE TABLE IF NOT EXISTS report_comments (
    report_id BLOB NOT NULL CHECK(length(report_id) = 16) REFERENCES reports(report_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, comment_id)
) STRICT;

CREATE TABLE IF NOT EXISTS event_comments (
    event_id BLOB NOT NULL CHECK(length(event_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, comment_id)
) STRICT;

-- Optional provenance layer for raw CSV rows or document chunks used during ingestion.
CREATE TABLE IF NOT EXISTS raw_records (
    raw_hash BLOB PRIMARY KEY,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    source_name TEXT,
    row_number INTEGER,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_transfers_date ON transfers(date);
CREATE INDEX IF NOT EXISTS idx_transfers_asset ON transfers(asset_symbol);
CREATE INDEX IF NOT EXISTS idx_transfers_sender ON transfers(sender_account_id);
CREATE INDEX IF NOT EXISTS idx_transfers_receiver ON transfers(receiver_account_id);
CREATE INDEX IF NOT EXISTS idx_statements_account_asset_date ON statements(account_id, asset_symbol, date);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);
CREATE INDEX IF NOT EXISTS idx_comments_type ON comments(type);
