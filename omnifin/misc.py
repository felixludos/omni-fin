from pathlib import Path
import sqlite3
import omnifig as fig


def get_path(cfg: fig.Configuration,
			 path_key='path', root_key='root',
			 path_default=None, root_default=None,
			 *, silent=True) -> Path:
	if not isinstance(path_key, (list, tuple)):
		path_key = [path_key]
	if not isinstance(root_key, (list, tuple)):
		root_key = [root_key]
	root = cfg.pulls(*root_key, default=root_default, silent=silent)
	if root is not None:
		root = Path(root)

	path = cfg.pulls(*path_key, default=path_default, silent=silent)
	if path is not None:
		path = Path(path)
		if root is not None:
			path = root / path

	return path



@fig.autocomponent('repo-root')
def repo_root() -> Path:
	"""Returns the root directory of the repository."""
	return Path(__file__).parent.parent



@fig.autocomponent('assets-root')
def assets_root() -> Path:
	"""Returns the root directory of the assets."""
	return repo_root() / 'assets'



def load_db(path: Path | None = None):
	# if path is not None and not path.exists():
	# 	raise FileNotFoundError("Database file not found.")
	if path is None:
		db_root = repo_root() / 'db'
		db_root.mkdir(exist_ok=True, parents=True)
		path = db_root / 'omnifin.db'

	conn = sqlite3.connect(path)
	return conn


