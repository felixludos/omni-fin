from .imports import *

from .misc import get_path, load_csv_rows
from .parsers import Parser
from .datacls import Record, Transaction
from .writing import create_report


class Rule:
	def select(self, txn: Transaction) -> bool:
		return True

	def plan(self, txns: list[Transaction]) -> None:
		pass

	def judge(self, txn: Transaction) -> tuple[str, str] | None:
		pass



def select_txns(cfg: fig.Configuration) -> list[Transaction] | None:

	quarter = cfg.pull('quarter', None)

	year = cfg.pull('year', None)
	if year is not None:
		if year == 'all':
			return list(Transaction.find_all())

		try:
			year = int(year)
		except ValueError:
			raise ValueError(f'Invalid year: {year}')

		if quarter is not None:
			try:
				quarter = int(quarter)
			except ValueError:
				raise ValueError(f'Invalid quarter: {quarter}')

		def filter_txn(txn: Transaction):
			return txn.date.year == year and (quarter is None or (txn.date.month-1) // 3 + 1 == quarter)
		return list(filter(filter_txn, Transaction.find_all()))



@fig.script('validate')
def validate(cfg: fig.Configuration):
	"""Validates the data."""
	conn = cfg.pull('conn')
	Record.set_conn(conn)

	rule: Rule = cfg.pull('rule')

	txns = select_txns(cfg)
	if txns is None:
		txns = list(Transaction.find_all())

	txns = [txn for txn in txns if rule.select(txn)]
	cfg.print(f'Validating {len(txns)} transactions.')

	# Load Update
	path = get_path(cfg, path_key='update', root_key='root')
	update = []
	if path is not None:
		# load csv file with pandas
		update = load_csv_rows(path)

	selected = []
	verdicts = Counter()

	pbar = tqdm(txns)
	for txn in pbar:
		verdict = rule.judge(txn)
		if verdict is not None:
			cat, desc = verdict
			verdicts[cat] += 1
			selected.append((txn, cat, desc))
		viz = ', '.join(f'{k}: {v}' for k, v in verdicts.items())
		if not len(viz):
			viz = '(No verdicts)'
		pbar.set_description(viz)

	report = create_report(cfg)

	# Commit the changes
	conn.commit()

	cfg.print('Validation complete.')










