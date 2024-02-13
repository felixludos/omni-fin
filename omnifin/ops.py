from .imports import *

from .misc import get_path, load_db
from .building import init_db
from .datacls import Asset, Account



@fig.script('init-db')
def create_db(cfg: fig.Configuration):
	path = get_path(cfg, path_key='path', root_key='root')
	if path is None:
		raise ValueError('Database path not specified.')

	conn = load_db(path)
	init_db(conn)
	conn.commit()

	assets_path = get_path(cfg, path_key='init-assets', root_key='root')
	if assets_path is not None and assets_path.exists():
		items = load_yaml(assets_path)
		cfg.print(f'Loaded {len(items)} assets from {assets_path}.')
		for item in items:
			Asset(**item).write(conn)
		conn.commit()

	accounts_path = get_path(cfg, path_key='init-accounts', root_key='root')
	if accounts_path is not None and accounts_path.exists():
		items = load_yaml(accounts_path)
		cfg.print(f'Loaded {len(items)} accounts from {accounts_path}.')
		for item in items:
			Account(**item).write(conn)
		conn.commit()

	cfg.print(f'Setup database file {path}.')
	return conn








