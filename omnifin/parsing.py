from pathlib import Path
from tqdm import tqdm
from omnibelt import save_json
import omnifig as fig
# import csv
import pandas as pd

from . import misc
# from .datcls import Record, Report, Transaction, Account, Asset, Tag, Statement



class ParseError(ValueError):
	pass



class Parser(fig.Configurable):
	_ParseError = ParseError

	def load(self, path: Path) -> pd.DataFrame:
		return pd.read_csv(path)


	def parse(self, info: dict) -> dict | None:
		raise NotImplementedError


	def cleanup(self, outpath, entries):
		pass



@fig.script('parse-csv', description='Parse a CSV file into a json file (usually of transactions).')
def parse_csv(cfg: fig.Configuration):
	path = misc.get_path(cfg, path_key='path', root_key='root')
	if not path.exists():
		raise FileNotFoundError(f'File {path} not found.')

	outpath = misc.get_path(cfg, path_key='out', root_key='root')
	if outpath is None:
		outpath = path.parent / f'{path.stem}.json'
	if outpath.exists() and not cfg.pull('overwrite', False):
		raise FileExistsError(f'File {outpath} already exists.')

	parser: Parser = cfg.pull('parser')

	cfg.print(f'Loading and parsing {path}')

	df = parser.load(path)

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
		cfg.print(f'Saved failed entries to {outpath.parent / f"{outpath.stem}-failed{outpath.suffix}"}')

	parser.cleanup(outpath, entries)
	save_json(entries, outpath)
	cfg.print(f'Saved to {outpath}')

	return entries, failed











