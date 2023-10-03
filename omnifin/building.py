import sqlite3


def init_db(conn: sqlite3.Connection):
    """Initialize the database with tables."""
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        associated_account INTEGER,
        description TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (associated_account) REFERENCES accounts(id)
    );
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at);
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_name TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        description TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_name TEXT NOT NULL UNIQUE,
        category TEXT,
        description TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_name TEXT NOT NULL,
        account_type TEXT NOT NULL,
        account_owner TEXT,
        description TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS statements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dateof DATE NOT NULL,
        account INTEGER NOT NULL,
        balance REAL NOT NULL,
        unit INTEGER NOT NULL,
        description TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (account) REFERENCES accounts(id),
        FOREIGN KEY (unit) REFERENCES assets(id),
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dateof DATE NOT NULL,
        location TEXT,
        sender INTEGER NOT NULL,
        amount REAL NOT NULL,
        unit INTEGER NOT NULL,
        receiver INTEGER NOT NULL,
        received_amount REAL,
        received_unit INTEGER,
        description TEXT,
        reference TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (unit) REFERENCES assets(id),
        FOREIGN KEY (received_unit) REFERENCES assets(id),
        FOREIGN KEY (sender) REFERENCES accounts(id),
        FOREIGN KEY (receiver) REFERENCES accounts(id),
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_transactions_dateof ON transactions(dateof);
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS transaction_links (
        id1 INTEGER NOT NULL,
        id2 INTEGER NOT NULL,
        link_type TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (id1) REFERENCES transactions(id),
        FOREIGN KEY (id2) REFERENCES transactions(id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(id1, id2)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS statement_links (
        id1 INTEGER NOT NULL,
        id2 INTEGER NOT NULL,
        link_type TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (id1) REFERENCES statements(id),
        FOREIGN KEY (id2) REFERENCES statements(id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(id1, id2)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS transaction_tags (
        id INTEGER,
        tag_id INTEGER,
        report INTEGER NOT NULL,
        FOREIGN KEY (id) REFERENCES transactions(id),
        FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(id, tag_id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS statement_tags (
        id INTEGER,
        tag_id INTEGER,
        report INTEGER NOT NULL,
        FOREIGN KEY (id) REFERENCES statements(id),
        FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(id, tag_id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS account_tags (
        id INTEGER,
        tag_id INTEGER,
        report INTEGER NOT NULL,
        FOREIGN KEY (id) REFERENCES accounts(id),
        FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(id, tag_id)
    );
    """)

    conn.commit()


