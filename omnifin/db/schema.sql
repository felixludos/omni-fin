-- Omnifin Ledger Schema (v2)
-- SQLite STRICT mode + foreign keys enabled by default for all tables.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================================
-- Provenance & schema versioning
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
) STRICT;

-- Import/edit sessions. Each ingestion or manual edit produces one row here.
-- Additional context/notes should be attached via the comments table (type-based).
CREATE TABLE IF NOT EXISTS reports (
    report_id BLOB PRIMARY KEY CHECK(length(report_id) = 16),
    date TEXT NOT NULL,
    name TEXT,
    author TEXT,
    raw_hash BLOB
) STRICT;

-- ============================================================================
-- Core entities
-- ============================================================================

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
    type TEXT,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

-- Entities: additional info like tax_id/jurisdiction attached via comments/tags.
CREATE TABLE IF NOT EXISTS entities (
    entity_id BLOB PRIMARY KEY CHECK(length(entity_id) = 16),
    name TEXT NOT NULL UNIQUE,
    legal_type TEXT
) STRICT;

-- ============================================================================
-- Statements & Transfers
-- ============================================================================

-- currency_code is redundant with asset_symbol (e.g., AAPL implies USD).
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

-- ============================================================================
-- Transfer matching (reconciliation)
-- ============================================================================

CREATE TABLE IF NOT EXISTS transfer_matches (
    source_transfer_id BLOB NOT NULL CHECK(length(source_transfer_id) = 16),
    receiver_transfer_id BLOB NOT NULL CHECK(length(receiver_transfer_id) = 16),
    FOREIGN KEY(source_transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    FOREIGN KEY(receiver_transfer_id) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    PRIMARY KEY (source_transfer_id, receiver_transfer_id),
    CHECK(source_transfer_id != receiver_transfer_id)
) STRICT;

-- ============================================================================
-- Locations & transfer associations
-- ============================================================================

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

-- ============================================================================
-- Events & transactions
-- ============================================================================

CREATE TABLE IF NOT EXISTS events (
    event_id BLOB PRIMARY KEY CHECK(length(event_id) = 16),
    name TEXT UNIQUE,
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

-- ============================================================================
-- Entity ↔ Account associations
-- ============================================================================

CREATE TABLE IF NOT EXISTS entity_accounts (
    entity_id BLOB NOT NULL CHECK(length(entity_id) = 16) REFERENCES entities(entity_id) ON DELETE CASCADE,
    account_id BLOB NOT NULL CHECK(length(account_id) = 16) REFERENCES accounts(account_id) ON DELETE CASCADE,
    relationship TEXT,
    PRIMARY KEY (entity_id, account_id)
) STRICT;

-- ============================================================================
-- Tags & tag associations
-- ============================================================================

CREATE TABLE IF NOT EXISTS tags (
    tag_id BLOB PRIMARY KEY CHECK(length(tag_id) = 16),
    name TEXT NOT NULL,
    category TEXT,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

-- Asset ↔ Tag
CREATE TABLE IF NOT EXISTS asset_tags (
    asset_symbol TEXT NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (asset_symbol, tag_id)
) STRICT;

-- Account ↔ Tag
CREATE TABLE IF NOT EXISTS account_tags (
    account_id BLOB NOT NULL CHECK(length(account_id) = 16) REFERENCES accounts(account_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, tag_id)
) STRICT;

-- Transfer ↔ Tag
CREATE TABLE IF NOT EXISTS transfer_tags (
    transfer_id BLOB NOT NULL CHECK(length(transfer_id) = 16) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (transfer_id, tag_id)
) STRICT;

-- Statement ↔ Tag
CREATE TABLE IF NOT EXISTS statement_tags (
    statement_id BLOB NOT NULL CHECK(length(statement_id) = 16) REFERENCES statements(statement_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (statement_id, tag_id)
) STRICT;

-- Event ↔ Tag
CREATE TABLE IF NOT EXISTS event_tags (
    event_id BLOB NOT NULL CHECK(length(event_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, tag_id)
) STRICT;

-- Report ↔ Tag
CREATE TABLE IF NOT EXISTS report_tags (
    report_id BLOB NOT NULL CHECK(length(report_id) = 16) REFERENCES reports(report_id) ON DELETE CASCADE,
    tag_id BLOB NOT NULL CHECK(length(tag_id) = 16) REFERENCES tags(tag_id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, tag_id)
) STRICT;

-- Notes attached to reports use comments with type-based annotations.

-- ============================================================================
-- Comments & comment associations
-- ============================================================================

CREATE TABLE IF NOT EXISTS comments (
    comment_id BLOB PRIMARY KEY CHECK(length(comment_id) = 16),
    content TEXT NOT NULL,
    type TEXT,
    created_at TEXT NOT NULL,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

-- Asset ↔ Comment
CREATE TABLE IF NOT EXISTS asset_comments (
    asset_symbol TEXT NOT NULL REFERENCES assets(symbol) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (asset_symbol, comment_id)
) STRICT;

-- Account ↔ Comment
CREATE TABLE IF NOT EXISTS account_comments (
    account_id BLOB NOT NULL CHECK(length(account_id) = 16) REFERENCES accounts(account_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (account_id, comment_id)
) STRICT;

-- Transfer ↔ Comment
CREATE TABLE IF NOT EXISTS transfer_comments (
    transfer_id BLOB NOT NULL CHECK(length(transfer_id) = 16) REFERENCES transfers(transfer_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (transfer_id, comment_id)
) STRICT;

-- Statement ↔ Comment
CREATE TABLE IF NOT EXISTS statement_comments (
    statement_id BLOB NOT NULL CHECK(length(statement_id) = 16) REFERENCES statements(statement_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (statement_id, comment_id)
) STRICT;

-- Report ↔ Comment
CREATE TABLE IF NOT EXISTS report_comments (
    report_id BLOB NOT NULL CHECK(length(report_id) = 16) REFERENCES reports(report_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (report_id, comment_id)
) STRICT;

-- Event ↔ Comment
CREATE TABLE IF NOT EXISTS event_comments (
    event_id BLOB NOT NULL CHECK(length(event_id) = 16) REFERENCES events(event_id) ON DELETE CASCADE,
    comment_id BLOB NOT NULL CHECK(length(comment_id) = 16) REFERENCES comments(comment_id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, comment_id)
) STRICT;

-- ============================================================================
-- Raw record provenance layer for ingestion tracking
-- ============================================================================

CREATE TABLE IF NOT EXISTS raw_records (
    raw_hash BLOB PRIMARY KEY,
    report_id BLOB CHECK(report_id IS NULL OR length(report_id) = 16),
    source_name TEXT,
    row_number INTEGER,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY(report_id) REFERENCES reports(report_id)
) STRICT;

-- ============================================================================
-- Indexes for provenance queries, reconciliation lookups, and junction tables
-- ============================================================================

-- Transfer lookups by date / asset / accounts
CREATE INDEX IF NOT EXISTS idx_transfers_date ON transfers(date);
CREATE INDEX IF NOT EXISTS idx_transfers_asset ON transfers(asset_symbol);
CREATE INDEX IF NOT EXISTS idx_transfers_sender ON transfers(sender_account_id);
CREATE INDEX IF NOT EXISTS idx_transfers_receiver ON transfers(receiver_account_id);
-- Combined index for reconciliation (sender↔receiver lookups)
CREATE INDEX IF NOT EXISTS idx_transfers_sender_receiver_date ON transfers(sender_account_id, receiver_account_id, date);

-- Statement lookups by account + asset + date
CREATE INDEX IF NOT EXISTS idx_statements_account_asset_date ON statements(account_id, asset_symbol, date);

-- Tags by name / category (for deduplication and filtering)
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category);

-- Asset lookups by category
CREATE INDEX IF NOT EXISTS idx_assets_category ON assets(category);

-- Comments by type (for metadata extraction queries)
CREATE INDEX IF NOT EXISTS idx_comments_type ON comments(type);

-- Junction table lookups for faster event/transfer matching
CREATE INDEX IF NOT EXISTS idx_transactions_event ON transactions(event_id);
CREATE INDEX IF NOT EXISTS idx_entity_accounts_entity ON entity_accounts(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_accounts_account ON entity_accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_event_links_event_2 ON event_links(event_2_id);

-- Report provenance lookups (fast filter by import session)
CREATE INDEX IF NOT EXISTS idx_tags_report ON tags(report_id);
CREATE INDEX IF NOT EXISTS idx_comments_report ON comments(report_id);
CREATE INDEX IF NOT EXISTS idx_assets_report ON assets(report_id);
CREATE INDEX IF NOT EXISTS idx_accounts_report ON accounts(report_id);
CREATE INDEX IF NOT EXISTS idx_raw_records_report ON raw_records(report_id);

-- Asset tag lookup optimization (for Investment db_all query)
CREATE INDEX IF NOT EXISTS idx_asset_tags_symbol ON asset_tags(asset_symbol);