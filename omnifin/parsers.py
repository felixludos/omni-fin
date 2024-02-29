from .imports import *

from .misc import get_path, load_db, load_item_file, format_amount
from .building import init_db
from .datacls import Record, Asset, Account, Report, Transaction, Verification, Tag


class Parser(fig.Configurable):
	def load_items(self, path: Path):
		return load_item_file(path)

	def prepare(self, account: Account, items: Iterable[dict]):
		self.account = account
		return []

	def parse(self, item: dict, tags: dict[str, list[Record]]):
		raise NotImplementedError



@fig.component('amazon')
class Amazon(Parser):
	def prepare(self, account: Account, items: Iterable[dict]):
		recs = super().prepare(account, items)
		recs.extend([
			Tag(name='amazon', category='amazon', description='orders fulfilled by amazon directly'),
			Tag(name='marketplace', category='amazon', description='orders fulfilled by 3rd party sellers'),
		])
		return recs


	def parse(self, item: dict, tags: dict[str, list[Record]]):
		if isinstance(item['Receiver'], str):
			txn = Transaction(sender=self.account, receiver=item['Receiver'])
		else:
			txn = Verification(sender=item['Sender'], receiver=self.account)

		date = datetime.strptime(item['Transaction Date'], '%m/%d/%Y').date()
		txn.date = date

		txn.amount = format_amount(item['Amount'])
		txn.unit = 'usd'

		txn.description = item['Description']
		txn.reference = item['Reference']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('bank99')
class Bank99(Parser):
	def load_items(self, path: Path):
		return list(load_csv_rows(path, delimiter=';'))


	def parse(self, item: dict, tags: dict[str, list[Record]]):

		txn = Transaction()

		if item['Sender'] is None:
			txn.sender = self.account
			txn.receiver = item['Receiver']
		else:
			txn.sender = item['Sender']
			txn.receiver = self.account

		txn.date = datetime.strptime(item['Buchungsdatum'], '%Y-%m-%d').date()

		txn.amount = format_amount(item['Betrag'])
		txn.unit = 'eur'

		txn.description = item['Notes']
		txn.reference = item['Eigene Referenz']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn














