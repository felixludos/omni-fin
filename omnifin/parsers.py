from .imports import *

from .misc import get_path, load_db, load_item_file
from .building import init_db
from .datacls import Record, Asset, Account, Report, Transaction, Verification, Tag


class Parser(fig.Configurable):
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

		txn.amount = abs(float(item['Amount']))
		txn.unit = 'usd'

		if isinstance(item['Description'], str):
			txn.description = item['Description']
		if isinstance(item['Reference'], str):
			txn.reference = item['Reference']
		if isinstance(item['Location'], str):
			txn.location = item['Location']

		if isinstance(item['Tags'], str):
			for tag in item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn


















