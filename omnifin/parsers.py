from .imports import *

from .misc import get_path, load_db, load_item_file, format_amount, MCC
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



@fig.component('becu')
class BECU(Parser):
	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])

		txn = Transaction() if sender is None or sender.owner == 'external' \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if item['Receiver'] is None else item['Receiver']

		txn.date = datetime.strptime(item['Date'], '%m/%d/%Y').date()

		txn.amount = format_amount(item['Debit' if sender is None else 'Credit'])
		txn.unit = 'usd'

		txn.description = item['Notes']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('boa')
class BOA(Parser):
	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])

		txn = Transaction() if sender is None or sender.owner == 'external' \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if item['Receiver'] is None else item['Receiver']

		txn.date = datetime.strptime(item['Date'], '%m/%d/%Y').date()

		txn.amount = format_amount(item['Amount'].replace(',', '')) if isinstance(item['Amount'], str) \
			else abs(float(item['Amount']))
		txn.unit = 'usd'

		txn.description = item['Notes']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



class MCC_Parser(Parser):
	def extract_mcc_tags(self, tags: Iterable[str]):
		existing = set()
		mcc = MCC()
		concepts = []
		for tag in tags:
			if tag not in existing and (mcc_tag := mcc.find(tag)) is not None:
				concepts.append(Tag(name=tag, category='MCC', description=mcc_tag['edited_description']))
			existing.add(tag)
		return concepts

	def prepare(self, account: Account, items: Iterable[dict]):
		concepts = super().prepare(account, items)
		candidates = Counter(tag for item in items if item['Tags'] is not None for tag in
							(item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(',')))
		concepts.extend(self.extract_mcc_tags(candidates))
		return concepts



@fig.component('cap1')
class CapitalOne(MCC_Parser):
	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])

		txn = Transaction() if sender is None or sender.owner == 'external' \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if item['Receiver'] is None else item['Receiver']

		txn.date = datetime.strptime(item['Transaction Date'], '%Y-%m-%d').date()

		txn.amount = abs(float(item['Debit' if sender is None else 'Credit']))
		txn.unit = 'usd'

		txn.description = item['Description']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('usbank')
class USBank(MCC_Parser):
	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])

		txn = Transaction() if sender is None or sender.owner == 'external' \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if item['Receiver'] is None else item['Receiver']

		txn.date = datetime.strptime(item['Date'], '%Y-%m-%d').date()

		txn.amount = format_amount(item['Amount'])
		txn.unit = 'usd'

		notes = item['Notes']
		if notes is not None and '%out-asset' in notes:
			received = notes.split(' %out-asset ')[-1].strip()
			terms = received.split(' ')
			assert len(terms) == 2
			num, cur = terms
			txn.received_unit = cur
			txn.received_amount = abs(float(num))

		txn.description = item['Name']
		txn.location = item['Location']
		txn.reference = item['Reference']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('commerz')
class Commerzbank(MCC_Parser):
	def load_items(self, path: Path):
		return list(load_csv_rows(path, delimiter=';'))

	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])
		receiver = Account.find(item['Receiver'])

		txn = Transaction() if (sender is None or sender.owner == 'external'
								or (receiver is not None and receiver.name == 'cash')) \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if receiver is None else receiver

		txn.date = datetime.strptime(item['Buchungstag'], '%d.%m.%Y').date()

		txn.amount = format_amount(item['Betrag'])
		txn.unit = item['Währung']

		txn.description = item['Notes']
		txn.location = item['Location']
		txn.reference = item['Reference']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('costco')
class CostcoCredit(MCC_Parser):
	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])
		receiver = Account.find(item['Receiver'])

		txn = Transaction() if (sender is None or sender.owner == 'external'
								or (receiver is not None and receiver.name == 'cash')) \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if receiver is None else receiver

		txn.date = datetime.strptime(item['Date'], '%m/%d/%Y').date()

		txn.amount = abs(float(item['Debit' if sender is None else 'Credit']))
		txn.unit = 'usd'

		txn.description = item['Description']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('dkb')
class DKB(MCC_Parser):
	def load_items(self, path: Path):
		return list(load_csv_rows(path, delimiter=';'))

	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])
		receiver = Account.find(item['Receiver'])

		txn = Transaction() if (sender is None or sender.owner == 'external'
								or (receiver is not None and receiver.name == 'cash')) \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if receiver is None else receiver

		txn.date = datetime.strptime(item['Buchungsdatum'], '%d.%m.%y').date()

		txn.amount = format_amount(item['Betrag (€)'].replace('.', '').replace(',', '.'))
		txn.unit = 'eur'

		txn.description = item['Notes']
		txn.location = item['Location']
		txn.reference = item['Kundenreferenz']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('heritage')
class Heritage(Parser):
	def parse(self, item: dict, tags: dict[str, list[Record]]):

		sender = Account.find(item['Sender'])
		receiver = Account.find(item['Receiver'])

		txn = Transaction() if (sender is None or sender.owner == 'external'
								or (receiver is not None and receiver.name == 'cash')) \
			else Verification()

		txn.sender = self.account if sender is None else sender
		txn.receiver = self.account if receiver is None else receiver

		txn.date = datetime.strptime(item['Date'], '%m-%d-%Y').date()

		txn.amount = format_amount(item['Amount'])
		txn.unit = 'usd'

		txn.description = item['Description']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('ibkr')
class IBKR(Parser):
	def load_items(self, path: Path):
		lines = path.read_text(encoding='utf-8').split('\n')

		transfers = [line for line in lines if line.replace('"', '').startswith('Deposits & Withdrawals')]
		transfers = [line for line in transfers if not line.replace('"', '')
															.startswith('Deposits & Withdrawals,Data,Total')]
		csv = io.BytesIO()
		csv.write('\n'.join(transfers).encode('utf-8'))
		csv.seek(0)
		transfers = list(load_csv_rows(csv))
		csv.close()

		trades = [line for line in lines if line.replace('"', '').startswith('Trades')]
		trades = [line for line in trades if not line.replace('"', '').startswith('Trades,Total')]
		trades = [line for line in trades if not line.replace('"', '').startswith('Trades,SubTotal')]
		csv = io.BytesIO()
		csv.write('\n'.join(trades).encode('utf-8'))
		csv.seek(0)
		trades = list(load_csv_rows(csv))
		csv.close()

		return transfers + trades

	def parse(self, item: dict, tags: dict[str, list[Record]]):
		if 'Deposits & Withdrawals' in item:
			return self.parse_transfer(item, tags)
		elif 'Trades' in item:
			return self.parse_trade(item, tags)
		raise ValueError(f"Unknown item type: {item}")

	def parse_transfer(self, item: dict, tags: dict[str, list[Record]]):

		txn = Transaction()

		amt = item['Amount']
		currency = item['Currency']

		desc = item['Description']
		if currency == 'EUR':
			other = Account.find('bank99-gu')
		elif 'advance' in desc.lower() or 'cancellation' in desc.lower():
			other = Account.find('institution')
		elif '%account ' in desc:
			other = Account.find(desc.split('%account ')[-1].strip())
		elif 'NATL FIN SVC LLC' in desc or 'FID BKG SVC LLC' in desc:
			other = Account.find('fidelity')
		elif 'HERITAGE' in desc:
			other = Account.find('heritage')
		# elif currency == 'USD':
		# 	other = Account.find('bank99-3811')
		else:
			raise ValueError(f"Unknown account: {item}")

		txn.sender, txn.receiver = (self.account, other) if amt < 0 else (other, self.account)

		txn.amount = abs(amt)
		txn.unit = currency

		txn.date = datetime.strptime(item['Settle Date'], '%Y-%m-%d').date()

		txn.description = item['Description']
		txn.location = ',online'

		return txn


	def parse_trade(self, item: dict, tags: dict[str, list[Record]]):

		txn = Transaction()

		amt = item['Amount']

		txn.sender = self.account if amt < 0 else Account.find('market')
		txn.receiver = Account.find('market') if amt < 0 else self.account



		pass

		pass




@fig.component('fidelity')
class Fidelity(Parser):
	pass


