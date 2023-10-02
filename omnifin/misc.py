from pathlib import Path
import sqlite3



def repo_root() -> Path:
	"""Returns the root directory of the repository."""
	return Path(__file__).parent.parent



def load_db(path: Path | None = None):
	if path is not None and not path.exists():
		raise FileNotFoundError("Database file not found.")
	if path is None:
		db_root = repo_root() / 'db'
		db_root.mkdir(exist_ok=True, parents=True)
		path = db_root / 'omnifin.db'

	conn = sqlite3.connect(path)
	return conn


