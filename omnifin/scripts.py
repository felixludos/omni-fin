from pathlib import Path
from tqdm import tqdm
from tabulate import tabulate
from omnibelt import load_yaml, save_yaml, load_json, save_json
import omnifig as fig
from datetime import datetime
from dateutil import parser

from . import misc
from .datcls import Account, Asset, Tag, Report, Transaction
from .managing import FinanceManager
from .identification import Identifier, World



def get_manager(cfg: fig.Configuration = None) -> FinanceManager:
	if cfg is None:
		cfg = fig.create_config()
	cfg.push('manager._type', 'manager', overwrite=False, silent=True)
	m = cfg.pull('manager')

	Identifier._manager = m
	return m


def get_world(cfg: fig.Configuration = None):
	if cfg is None:
		cfg = fig.create_config()
	cfg.push('world._type', 'world', overwrite=False, silent=True)

	w: World = cfg.pull('world')

	path = misc.get_path(cfg, path_key='shortcut-path', root_key='root')
	if path is not None:
		shortcuts = load_yaml(path)
		w.asset_shortcuts.update(shortcuts.get('assets', {}))
		w.account_shortcuts.update(shortcuts.get('accounts', {}))

	return w


def setup_report(cfg: fig.Configuration):
	rep: Report | str = cfg.pull('report', 'manual')
	if isinstance(rep, str):
		rep = Report(category=rep)

	acc: Account | str = cfg.pull('account', None)
	if isinstance(acc, str):
		acc = Account(name=acc)
	if acc is not None:
		rep.account = acc

	acc = rep.account
	if acc is not None:
		acc_options = list(acc.fill())
		if len(acc_options) > 1:
			raise ValueError(f'Found multiple accounts matching {acc}: {acc_options}')
		elif len(acc_options) == 0:
			raise ValueError(f'Found no accounts matching {acc}')
		acc = acc_options[0]
		cfg.print(f'Using account {acc}')

	return rep



@fig.script('init-db')
def create_db(cfg: fig.Configuration):

	root = cfg.pull('root', None)
	if root is not None:
		root = Path(root)

	assets = cfg.pull('init-assets', None)
	accounts = cfg.pull('init-accounts', None)

	m = get_manager(cfg)

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
		print(f'Adding {len(new)}/{len(entries)} missing assets from {assets}.')
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

	print(f'Setup database file {m.path} and populated with {len(todo)} new records.')


@fig.script('statement')
def submit_statement(cfg: fig.Configuration):
	m = get_manager(cfg)
	m.initialize()

	date = cfg.pull('date',)
	date = parser.parse(date).date()
	# print(f'Using date {date}')
	# rep.date = datetime.now().strftime('%Y-%m-%d') if rep.date is None \
	# 	else parser.parse(rep.date).strftime('%Y-%m-%d')

	acc = cfg.pull('account', None)
	if acc is not None:
		acc = m.p(acc)

	# m.create_current('statement', account=acc)

	raise NotImplementedError



@fig.script('txns')
def submit_transactions(cfg: fig.Configuration):
	path = misc.get_path(cfg, path_key='path', root_key='root')
	if path is None:
		raise ValueError(f'No path of transactions specified.')
	if not path.exists():
		raise FileNotFoundError(f'File {path} not found.')

	entries = load_json(path)
	cfg.print(f'Loaded {len(entries)} entries from {path}')

	proc = cfg.pulls('processor', 'proc')

	m = get_manager(cfg)
	m.initialize()
	w = get_world(cfg)
	w.populate()
	cfg.print(f'Loaded database.')

	proc.prepare(w)

	rep: Report = setup_report(cfg)

	# cfg.print(f'Using report {rep} (associated with {"no account" if rep.account is None else rep.account})')
	cfg.print(f'Using report {rep}')

	strict = cfg.pull('strict', False)
	dry_run = cfg.pull('dry-run', False)

	new, skipped, errs = [], [], []

	pbar = cfg.pull('pbar', True, silent=True)
	itr = iter(entries)
	if pbar: itr = tqdm(itr, total=len(entries))
	for entry in itr:
		itr.set_description(f'new={len(new)}, errs={len(errs)}, skipped={len(skipped)}')
		try:
			txn = proc.process(entry)
		except Exception as e:
			raise e
			errs.append((entry, e))
		else:
			if txn is None:
				skipped.append(entry)
			else:
				if isinstance(txn, dict):
					txn = Transaction(**txn)
				assert isinstance(txn, Transaction), f'Invalid transaction type: {txn}'
				new.append(txn)

	if len(errs):
		tbl = tabulate([(err.__class__.__name__, str(err), str(entry))
			for entry, err in errs], headers=['error', 'message', 'entry'])

		cfg.print(tbl)
		cfg.print(f'Found {len(errs)} errors.')

	if len(skipped):
		cfg.print(f'Skipped {len(skipped)} entries.')

	if len(new) and not dry_run and (not strict or len(errs)+len(skipped) == 0):
		rep = m.write_report(rep)
		m.current_report = rep
		cfg.print(f'Adding {len(new)} new transactions with report {rep}')
		m.write_all(new, pbar=tqdm if pbar else None)
	else:
		cfg.print(f'Found {len(new)} new transactions. Not writing anything.')

	return new, skipped, errs


@fig.script('undo')
def undo_report(cfg: fig.Configuration):



	pass



