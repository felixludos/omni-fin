import io

from .imports import *

from .misc import get_path, load_db, load_item_file
from .building import init_db
from .parsers import Parser
from .datacls import Record, Asset, Account, Report, Tag, Transaction, Tagged, Linkable, Reportable


@fig.component('sqlite')
def form_connection(cfg: fig.Configuration):
	path = get_path(cfg, path_key='db', root_key='root')
	if path is None:
		raise ValueError('Database path not specified.')

	cfg.print(f'Database path: {path}')

	conn = load_db(path)
	Record.set_conn(conn)

	shortcut_path = get_path(cfg, path_key='shortcut-path', root_key='root')
	if shortcut_path is not None:
		shortcuts = load_yaml(shortcut_path)
		Asset.update_shortcuts(shortcuts.get('assets', {}))
		Account.update_shortcuts(shortcuts.get('accounts', {}))

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

	# cfg.print(f'Using report: {report}.')
	return report



@fig.script('init-db')
def create_db(cfg: fig.Configuration):
	# conn = form_connection(cfg)
	# cfg.push('conn._type', 'sqlite', silent=True, overwrite=False)
	conn = cfg.pull('conn')
	init_db(conn)
	# conn.commit()

	report = create_report(cfg)
	cfg.print(f'Using report: {report}.')
	report.write()

	assets_path = get_path(cfg, path_key='init-assets', root_key='root')
	if assets_path is not None and assets_path.exists():
		items = load_yaml(assets_path)
		cfg.print(f'Loaded {len(items)} assets from {assets_path}.')
		for item in items:
			Asset(**item).write_missing(report)
		# conn.commit()

	accounts_path = get_path(cfg, path_key='init-accounts', root_key='root')
	if accounts_path is not None and accounts_path.exists():
		items = load_yaml(accounts_path)
		cfg.print(f'Loaded {len(items)} accounts from {accounts_path}.')
		for item in items:
			Account(**item).write_missing(report)
		# conn.commit()

	tags_path = get_path(cfg, path_key='init-tags', root_key='root')
	if tags_path is not None and tags_path.exists():
		items = load_yaml(tags_path)
		cfg.print(f'Loaded {len(items)} tags from {tags_path}.')
		for item in items:
			Tag(**item).write_missing(report)
		# conn.commit()

	cfg.print('Database setup.')
	conn.commit()
	return conn



@fig.script('txn')
def add_transactions(cfg: fig.Configuration):
	conn = cfg.pull('conn')
	# conn = form_connection(cfg)
	report = create_report(cfg)

	account = None
	accountname = cfg.pull('account', None)
	if accountname is not None:
		account = Account.find(accountname)
	# cfg.print(f'Using account: {account}')

	report.account = account
	report.write()
	cfg.print(f'Using report: {report}.')

	path = get_path(cfg, path_key='path', root_key='root')

	cfg.push('parser._type', accountname, silent=True, overwrite=False)
	parser: Parser = cfg.pull('parser')

	items = parser.load_items(path)

	cfg.print(f'Loaded {len(items)} items from {path}')

	skip_commit = cfg.pull('skip-commit', False)
	skip_confirm = (cfg.pull('skip-confirm', False, silent=True)
					or cfg.pulls('yes', 'y', default=False, silent=True))
	if skip_confirm:
		cfg.print(f'Will not confirm before writing records.')
	if skip_commit:
		cfg.print(f'Will not commit changes to database.')

	concepts = parser.prepare(account, items)
	for concept in concepts:
		concept.write_missing(report)

	records: list[Reportable] = []
	tags: dict[str, list[Tagged]] = {}
	links: dict[str, list[list[Linkable]]] = {}

	pbar = cfg.pull('pbar', True)
	itr = tqdm(items) if pbar else items
	for item in itr:
		record = parser.parse(item, tags, links)
		if record is not None:
			# record.write(report)
			if isinstance(record, (list, tuple)):
				records.extend(record)
			else:
				records.append(record)

	parser.finish(records, tags, links)

	for rec in records:
		if isinstance(rec, Transaction):
			assert rec.amount is not None and rec.amount >= 0, f'Amount not set for {rec}'
			assert rec.received_amount is None or rec.received_amount > 0, f'Received amount not set for {rec}'

	for rec in records:
		rec.write(report)

	for tag, recs in tags.items():
		for rec in recs:
			rec.add_tags(report, tag)

	for category, groups in links.items():
		for group in groups:
			group = [txn for txn in group if isinstance(txn, Transaction)]
			if len(group) > 1:
				link, *others = group
				link.add_links(report, *others, category=category)

	if not skip_confirm:
		while True:
			cfg.print(f'Write {len(records)} records? ([y]/n): ')
			val = input().strip().lower()
			if val.startswith('y'):
				break
			elif val.startswith('n'):
				cfg.print('Aborted.')
				return records

	cfg.print(f'Writing {len(records)} records.')

	if not skip_commit:
		conn.commit()

	cfg.print(f'{len(records)} records saved.')
	return records



@fig.script('full-reset')
def multiple_txn(cfg: fig.Configuration):

	init_db(cfg)

	conn = cfg.pull('conn')

	pbar = cfg.pull('multi-pbar', True)

	cfg.push('skip-commit', True, silent=True, overwrite=False)
	cfg.push('skip-confirm', True, silent=True, overwrite=False)

	todo = list(cfg.peek('txn').peek_children())

	itr = tqdm(todo) if pbar else todo

	for item in itr:
		account = item.pull('account', None, silent=True)
		if pbar:
			itr.set_description(f'Account: {account}')

		with cfg.silence(True):
			add_transactions(item)

	cfg.print(f'Finished writing all transactions, now committing changes to database.')
	conn.commit()
	cfg.print(f'Committed all written records.')












