import sqlite3



import sqlite3

def init_db(conn: sqlite3.Connection):
    """Initialize the database with tables."""
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_name TEXT NOT NULL,
        category TEXT NOT NULL,
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
        category TEXT NOT NULL,
        description TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dateof DATE NOT NULL,
        category TEXT NOT NULL,
        associated_account INTEGER,
        description TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (associated_account) REFERENCES accounts(id)
    );
    """)
    c.execute("""
    CREATE INDEX IF NOT EXISTS idx_reports_dateof ON reports(dateof);
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        tag_id INTEGER PRIMARY KEY AUTOINCREMENT,
        tag_name TEXT NOT NULL UNIQUE,
        description TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (report) REFERENCES reports(id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS transaction_tags (
        transaction_id INTEGER,
        tag_id INTEGER,
        report INTEGER NOT NULL,
        FOREIGN KEY (transaction_id) REFERENCES transactions(id),
        FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(transaction_id, tag_id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS statement_tags (
        statement_id INTEGER,
        tag_id INTEGER,
        report INTEGER NOT NULL,
        FOREIGN KEY (statement_id) REFERENCES statements(id),
        FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(statement_id, tag_id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS account_tags (
        account_id INTEGER,
        tag_id INTEGER,
        report INTEGER NOT NULL,
        FOREIGN KEY (account_id) REFERENCES accounts(id),
        FOREIGN KEY (tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY (report) REFERENCES reports(id),
        PRIMARY KEY(account_id, tag_id)
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS statements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dateof DATE NOT NULL,
        account INTEGER NOT NULL,
        balance REAL NOT NULL,
        unit INTEGER NOT NULL,
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
        description TEXT,
        quantity REAL NOT NULL,
        unit INTEGER NOT NULL,
        received_amount REAL,
        received_unit INTEGER,
        sender INTEGER NOT NULL,
        receiver INTEGER NOT NULL,
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
    CREATE TABLE IF NOT EXISTS links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction1 INTEGER NOT NULL,
        transaction2 INTEGER NOT NULL,
        link_type TEXT,
        report INTEGER NOT NULL,
        FOREIGN KEY (transaction1) REFERENCES transactions(id),
        FOREIGN KEY (transaction2) REFERENCES transactions(id),
        FOREIGN KEY (report) REFERENCES reports(id),
        UNIQUE(transaction1, transaction2)
    );
    """)
    conn.commit()


