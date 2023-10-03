from pathlib import Path
from tqdm import tqdm
from omnibelt import load_yaml, save_yaml
import omnifig as fig

from .datcls import Account, Asset, Tag



@fig.script('init-db')
def create_db(cfg: fig.Configuration):

	root = cfg.pull('root', None)
	if root is not None:
		root = Path(root)

	cfg.push('manager._type', 'manager', overwrite=False, silent=True)
	m = cfg.pull('manager')

	assets = cfg.pull('assets', None)
	accounts = cfg.pull('accounts', None)

	if m.path.exists():
		print(f'Database file {m.path} already exists.')

	m.initialize()

	todo = []

	if assets is not None:
		assets = Path(assets)
		if root is not None:
			assets = root / assets
		if not assets.exists():
			raise FileNotFoundError(f'Asset file {assets} not found.')

		existing = {(a.name, a.category): a for a in Asset().fill()}
		if existing:
			print(f'Found existing {len(existing)} assets.')
		entries = load_yaml(assets)
		new = [Asset(**info) for info in entries
			   if (info.get('name'), info.get('category')) not in existing]
		print(f'Adding {len(new)}/{len(entries)} missing assets{} from {assets}.')
		todo.extend(new)

	if accounts is not None:
		accounts = Path(accounts)
		if root is not None:
			accounts = root / accounts
		if not accounts.exists():
			raise FileNotFoundError(f'Account file {accounts} not found.')

		existing = {(acc.name, acc.category, acc.owner): acc for acc in Account().fill()}
		if existing:
			print(f'Found existing {len(existing)} accounts.')
		entries = load_yaml(accounts)
		new = [Account(**info) for info in entries
			   if (info.get('name'), info.get('category'), info.get('owner')) not in existing]
		print(f'Adding {len(new)}/{len(entries)} missing accounts from {accounts}.')
		todo.extend(new)

	if len(todo):
		m.create_current('init')

		m.write_all(todo)






