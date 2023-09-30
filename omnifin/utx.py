from pathlib import Path
import sqlite3

# Universal transaction format (UTX) is a format for storing transactions using sqlite3.


def load_db(path: Path | None = None):
	if path is not None and not path.exists():
		raise FileNotFoundError("Database file not found.")
	if path is None:
		path = Path('fin-tx.db')

	conn = sqlite3.connect(path)
	return conn


def init_db(conn: sqlite3.Connection):
	"""Initialize the database with tables."""
	c = conn.cursor()
	c.execute("""
		CREATE TABLE IF NOT EXISTS tx (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			date DATE NOT NULL,
			description TEXT NOT NULL,
			quantity REAL NOT NULL,
			unit TEXT NOT NULL,
			category TEXT NOT NULL,
			subcategory TEXT NOT NULL,
			notes TEXT,
			created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
			updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
		)
	""")
	conn.commit()


