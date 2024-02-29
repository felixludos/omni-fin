from .imports import *

from .misc import get_path, load_db, load_item_file
from .building import init_db
from .parsers import Parser
from .datacls import Record, Asset, Account, Report



def form_connection(cfg: fig.Configuration):
	path = get_path(cfg, path_key='db', root_key='root')
	if path is None:
		raise ValueError('Database path not specified.')

	cfg.print(f'Database path: {path}')

	conn = load_db(path)
	Record.set_conn(conn)
	return conn



def create_report(cfg: fig.Configuration, desc: str = None) -> Report:
	script_name = None
	if desc is None:
		script_name = cfg.pull('_meta.script_name', None, silent=True)
		if script_name is not None:
			desc = f'created for {script_name!r} script'

	report = Report(category=cfg.pull('category', script_name or 'default'),
					# account=cfg.pull('account', None),
					description=cfg.pull('description', None) if desc is None else desc)

	cfg.print(f'Using report: {report}.')
	return report



@fig.script('init-db')
def create_db(cfg: fig.Configuration):
	conn = form_connection(cfg)
	init_db(conn)
	# conn.commit()

	report = create_report(cfg)
	report.write()

	assets_path = get_path(cfg, path_key='init-assets', root_key='root')
	if assets_path is not None and assets_path.exists():
		items = load_yaml(assets_path)
		cfg.print(f'Loaded {len(items)} assets from {assets_path}.')
		for item in items:
			Asset(**item).write(report)
		# conn.commit()

	accounts_path = get_path(cfg, path_key='init-accounts', root_key='root')
	if accounts_path is not None and accounts_path.exists():
		items = load_yaml(accounts_path)
		cfg.print(f'Loaded {len(items)} accounts from {accounts_path}.')
		for item in items:
			Account(**item).write(report)
		# conn.commit()

	cfg.print('Database setup.')
	conn.commit()
	return conn



@fig.script('txn')
def add_transactions(cfg: fig.Configuration):
	conn = form_connection(cfg)
	report = create_report(cfg)

	account = cfg.pull('account', None)
	if account is not None:
		account = Account.find(account)
	cfg.print(f'Using account: {account}')

	report.account = account
	report.write()

	path = get_path(cfg, path_key='path', root_key='root')

	items = load_item_file(path)

	cfg.print(f'Loaded {len(items)} items from {path}.')

	parser: Parser = cfg.pull('parser')
	cfg.print(f'Using parser: {parser}')

	parser.prepare(account, items)

	records = []

	pbar = cfg.pull('pbar', True)
	itr = tqdm(items) if pbar else items
	for item in itr:
		record = parser.parse(item)
		if record is not None:
			# record.write(report)
			if isinstance(record, list):
				records.extend(record)
			else:
				records.append(record)

	if not cfg.pulls('yes', 'y', default=False, silent=True):
		while True:
			cfg.print(f'Write {len(records)} records? ([y]/n): ')
			val = input().strip().lower()
			if val.startswith('y'):
				break
			elif val.startswith('n'):
				cfg.print('Aborted.')
				return records

	cfg.print(f'Writing {len(records)} records.')

	for rec in records:
		rec.write(report)

	conn.commit()

	cfg.print('Transactions added.')
	return records






