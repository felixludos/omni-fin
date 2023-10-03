from pathlib import Path
from tqdm import tqdm
from omnibelt import save_json
import omnifig as fig
# import csv
import pandas as pd

from . import misc
from .datcls import Record, Report, Transaction, Account, Asset, Tag, Statement


# @fig.script('csv-txn', description='Process a CSV file of transactions.')
def parse_csv_txn(cfg: fig.Configuration):
	path = misc.get_path(cfg, path_key='path', root_key='root')
	if not path.exists():
		raise FileNotFoundError(f'File {path} not found.')

	cfg.push('manager._type', 'manager', overwrite=False, silent=True)
	m = cfg.pull('manager')
	m.initialize()

	parser: Parser = cfg.pull('parser')

	data = parser.load(path)
	cfg.print(f'Loaded {len(data)} records with {parser}.')

	acc = cfg.pull('account', None)
	if isinstance(acc, Account):
		raise NotImplementedError
	elif acc is not None:
		acc = m.p(acc)

	rep = parser.as_report(path, data)
	if rep is None:
		rep = cfg.pull('report', None)
		if rep is None:
			rep = Report(category=cfg.pull('category', 'csv-txn-script'),
						 account=acc, description=f'parsing {path.absolute()}')
	if acc is not None:
		rep.account = acc

	if not cfg.pull('dry-run', False, silent=True):
		m.write_report(rep)
	m.current_report = rep

	cfg.print(f'Using report {rep}.')

	records = parser.parse(data)

	if len(records):
		if cfg.pull('dry-run', False, silent=True):
			print(f'DRY-RUN: Would have added {len(records)} records.')
		else:
			cfg.print(f'Adding {len(records)} records.')

			if not cfg.pull('confirm', False, silent=True):
				c = False
				while not c:
					c = input('Confirm? [Y/n] ').lower().strip() in {'', 'y', 'yes'}
					if not c:
						print('Aborting.')
						return

			m.write_all(records)

	else:
		cfg.print('No records to add.')

	parser.cleanup(records)

	return records



class ParseError(ValueError):
	pass



@fig.script('parse-csv', description='Parse a CSV file into a json file (usually of transactions).')
def parse_csv(cfg: fig.Configuration):
	path = misc.get_path(cfg, path_key='path', root_key='root')
	if not path.exists():
		raise FileNotFoundError(f'File {path} not found.')

	outpath = misc.get_path(cfg, path_key='out', root_key='root')
	if outpath.exists() and not cfg.pull('overwrite', False):
		raise FileExistsError(f'File {outpath} already exists.')

	parser: Parser = cfg.pull('parser')

	cfg.print(f'Loading and parsing {path}')

	df = pd.read_csv(path)

	itr = df.iterrows()
	pbar = cfg.pull('pbar', True, silent=True)
	if pbar:
		itr = tqdm(itr, total=len(df))

	entries, failed = [], []
	for index, row in itr:
		itr.set_description(f'ignored={index-len(entries)}, failed={len(failed)}')
		info = row.to_dict()
		try:
			entry = parser.parse(info)
		except ParseError as e:
			info['error'] = str(e)
			failed.append(info)
		else:
			if entry is not None:
				entries.append(entry)

	cfg.print(f'Parsed {len(entries)} entries, failed {len(failed)} entries.')

	if len(failed) and cfg.pull('save-failed', True):
		save_json(failed, outpath.parent / f'{outpath.stem}-failed{outpath.suffix}')

	save_json(entries, outpath)
	cfg.print(f'Saved to {outpath}')

	return entries, failed



class Parser(fig.Configurable):
	_ParseError = ParseError


	def parse(self, info: dict) -> dict | None:
		raise NotImplementedError













