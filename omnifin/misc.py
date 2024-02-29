from pathlib import Path
import sqlite3, json
from omnibelt import load_json, save_json, load_csv_rows, load_yaml
import omnifig as fig



def load_item_file(path):
	suffix = path.suffix.lower()
	if suffix == '.csv':
		return list(load_csv_rows(path))
	elif suffix == '.json':
		return load_json(path)
	elif suffix == '.yaml' or suffix == '.yml':
		return load_yaml(path)
	elif suffix == '.jsonl':
		return [json.loads(line) for line in path.open('r')]

	raise FileNotFoundError(f'Unknown file type: {path}')



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



def format_location(*, city: str = None, location: str = None, cat: str = None) -> str:
	city = city or ''
	location = location or ''
	cat = cat or ''

	if ',' in city or ',' in location or ',' in cat:
		raise ValueError(f"Commas are not allowed in location fields: {city!r}, {location!r}, {cat!r}")
	return ','.join([city, location, cat])



@fig.autocomponent('repo-root')
def repo_root() -> Path:
	"""Returns the root directory of the repository."""
	return Path(__file__).parent.parent



@fig.autocomponent('assets-root')
def assets_root() -> Path:
	"""Returns the root directory of the assets."""
	return repo_root() / 'assets'



@fig.autocomponent('data-root')
def data_root() -> Path:
	"""Returns the root directory of the assets."""
	return repo_root() / 'novo-data'



def load_db(path: Path | None = None):
	# if path is not None and not path.exists():
	# 	raise FileNotFoundError("Database file not found.")
	if path is None:
		db_root = repo_root() / 'db'
		db_root.mkdir(exist_ok=True, parents=True)
		path = db_root / 'omnifin.db'

	conn = sqlite3.connect(path)
	return conn



class MCC:
	def __init__(self):
		self.path = assets_root() / 'mcc_codes.json'
		self.full = load_json(self.path)
		self.codes = {v['mcc']: v for  v in self.full}

	def find(self, code: int | str):
		code = str(code).zfill(4)
		return self.codes.get(code, None)


