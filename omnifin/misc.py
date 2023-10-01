from pathlib import Path
import sqlite3


def load_db(path: Path | None = None):
	if path is not None and not path.exists():
		raise FileNotFoundError("Database file not found.")
	if path is None:
		path = Path('fin-tx.db')

	conn = sqlite3.connect(path)
	return conn
