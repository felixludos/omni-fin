from .imports import *

from .misc import get_path, load_db, load_item_file
from .building import init_db
from .datacls import Record, Asset, Account, Report, Transaction, Verification


class Parser(fig.Configurable):
	def prepare(self, account: Account, items: Iterable[dict]):
		self.account = account


	def parse(self, item: dict):
		raise NotImplementedError



@fig.component('amazon')
class Amazon(Parser):
	def parse(self, item: dict):

		date = datetime.strptime(item['Transaction Date'], '%m/%d/%Y').date()

		if item['Receiver']:
			txn = Transaction()

			txn.sender = self.account
			txn.receiver = item['Receiver']

		else:
			# txn = Verification()
			return

		txn.date = date

		txn.amount = abs(float(item['Amount']))
		txn.unit = 'usd'

		txn.description = item['Description']
		txn.reference = item['Reference']

		txn.location = item['Location']

		return txn


















