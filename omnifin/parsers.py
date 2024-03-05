from .imports import *

from .misc import get_path, load_db, load_item_file, format_european_amount, MCC, format_regular_amount
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

		txn.amount = format_european_amount(item['Amount'])
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

		txn.amount = format_european_amount(item['Betrag'])
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

		txn.amount = format_european_amount(item['Debit' if sender is None else 'Credit'])
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

		txn.amount = format_european_amount(item['Amount'].replace(',', '')) if isinstance(item['Amount'], str) \
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

		txn.amount = format_european_amount(item['Amount'])
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

		txn.amount = format_european_amount(item['Betrag'])
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

		txn.amount = format_european_amount(item['Betrag (€)'].replace('.', '').replace(',', '.'))
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

		txn.amount = format_european_amount(item['Amount'])
		txn.unit = 'usd'

		txn.description = item['Description']
		txn.location = item['Location']

		if item['Tags'] is not None:
			for tag in item['Tags'].split(';') if ';' in item['Tags'] else item['Tags'].split(','):
				tags.setdefault(tag, []).append(txn)

		return txn



@fig.component('ibkr')
class IBKR(Parser):
	def __init__(self, symbols_path: Path = None, symbol_map: dict | Path = None, **kwargs):
		if symbols_path is not None and isinstance(symbols_path, str):
			symbols_path = Path(symbols_path)
		if symbol_map is not None and isinstance(symbol_map, str):
			symbol_map = Path(symbol_map)
			symbol_map = load_yaml(symbol_map)
		super().__init__(**kwargs)
		symbols = None
		if symbols_path is not None and symbols_path.exists():
			raw = load_yaml(symbols_path)
			symbols = {(data['ibkr-contract']['symbol'], data['ibkr-contract']['currency']): k
					   for k, data in raw.items()}
			assert len(raw) == len(symbols)
		if symbol_map is not None:
			symbol_map = {(ibkr, curr): k for k, (ibkr, curr) in symbol_map.items()}
			if symbols is not None:
				symbols.update(symbol_map)
			else:
				symbols = symbol_map
		self.symbols = symbols
		self.symbols_path = symbols_path


	def prepare(self, account: Account, items: Iterable[dict]):
		recs = super().prepare(account, items)

		trades = [item for item in items if 'Trades' in item and item['Asset Category'] == 'Stocks']

		symbols = {self.sanitize_symbol(item['Symbol'], item['Currency']): (item['Symbol'], item['Currency'])
				   for item in trades}

		recs.extend([Asset(name=symbol, category='stock', description=f'{ibkr} {curr}')
					 for symbol, (ibkr, curr) in symbols.items()])

		return recs


	def load_items(self, path: Path):
		# input file should be the exported "Activity Statement" from IBKR in "csv format"
		lines = path.read_text(encoding='utf-8').split('\n')

		transfers = [line for line in lines if line.replace('"', '').startswith('Deposits & Withdrawals')]
		transfers = [line for line in transfers if not line.replace('"', '')
															.startswith('Deposits & Withdrawals,Data,Total')]
		csv = io.BytesIO()
		csv.write('\n'.join(transfers).encode('utf-8'))
		csv.seek(0)
		transfers = list(load_csv_rows(csv))
		csv.close()

		header = ('Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,C. Price,'
				  'Proceeds,Comm/Fee,Basis,Realized P/L,MTM P/L,Code')
		trades = [header] + [line for line in lines
								  if line.replace('"', '').startswith('Trades,Data,Order,Stocks')]
		csv = io.BytesIO()
		csv.write('\n'.join(trades).encode('utf-8'))
		csv.seek(0)
		trades = list(load_csv_rows(csv))
		csv.close()

		header = ('Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,T. Price,,Proceeds,'
				  'Comm in EUR,,,MTM in EUR,Code')
		forex = [header] + [line for line in lines
							if line.replace('"', '').startswith('Trades,Data,Order,Forex,')]
		csv = io.BytesIO()
		csv.write('\n'.join(forex).encode('utf-8'))
		csv.seek(0)
		forex = list(load_csv_rows(csv))
		csv.close()

		dividends = [line for line in lines if line.replace('"', '').startswith('Dividends')]
		dividends = [line for line in dividends if not line.replace('"', '').startswith('Dividends,Data,Total')]
		csv = io.BytesIO()
		csv.write('\n'.join(dividends).encode('utf-8'))
		csv.seek(0)
		dividends = list(load_csv_rows(csv))
		csv.close()

		interest = [line for line in lines if line.replace('"', '').startswith('Interest,')]
		interest = [line for line in interest if not line.replace('"', '').startswith('Interest,Data,Total')]
		csv = io.BytesIO()
		csv.write('\n'.join(interest).encode('utf-8'))
		csv.seek(0)
		interest = list(load_csv_rows(csv))
		csv.close()

		fees = [line for line in lines if line.replace('"', '').startswith('Transaction Fees,')]
		fees = [line for line in fees if not line.replace('"', '').startswith('Transaction Fees,Data,Total')]
		csv = io.BytesIO()
		csv.write('\n'.join(fees).encode('utf-8'))
		csv.seek(0)
		fees = list(load_csv_rows(csv))
		csv.close()

		withholding = [line for line in lines if line.replace('"', '').startswith('Withholding Tax,')]
		withholding = [line for line in withholding if not line.replace('"', '').startswith('Withholding Tax,Data,Total')]
		csv = io.BytesIO()
		csv.write('\n'.join(withholding).encode('utf-8'))
		csv.seek(0)
		withholding = list(load_csv_rows(csv))
		csv.close()

		missing = [item for item in trades if self.sanitize_symbol(item['Symbol'], item['Currency']) is None]

		if len(missing):
			symbols = {item['Symbol'] for item in missing}
			raise ValueError(f"Missing symbols: {symbols}")

		return transfers + trades + dividends + forex + interest + fees + withholding

	@staticmethod
	def to_number(val: str | int | float):
		return format_regular_amount(val)

	def parse(self, item: dict, tags: dict[str, list[Record]]):
		if 'Deposits & Withdrawals' in item:
			return self.parse_transfer(item, tags)
		elif 'Trades' in item and item['Asset Category'] == 'Stocks':
			return self.parse_trade(item, tags)
		elif 'Trades' in item and item['Asset Category'] == 'Forex':
			return self.parse_forex(item, tags)
		elif 'Dividends' in item:
			return self.parse_dividend(item, tags)
		elif 'Interest' in item:
			return self.parse_interest(item, tags)
		elif 'Transaction Fees' in item:
			return self.parse_transaction_tax(item, tags)
		elif 'Withholding Tax' in item:
			return self.parse_withholding(item, tags)
		raise ValueError(f"Unknown item type: {item}")

	def parse_withholding(self, item: dict, tags: dict[str, list[Record]]):

		amt = self.to_number(item['Amount'])

		txn = Transaction()

		txn.sender = self.account if amt < 0 else 'tax'
		txn.receiver = 'tax' if amt < 0 else self.account

		txn.date = datetime.strptime(item['Date'], '%Y-%m-%d').date()

		txn.amount = abs(amt)
		txn.unit = item['Currency']

		txn.description = item['Description']

		return txn

	def parse_transaction_tax(self, item: dict, tags: dict[str, list[Record]]):
		txn = Transaction()

		txn.sender = self.account
		txn.receiver = 'tax'

		date = datetime.strptime(item['Date/Time'], '%Y-%m-%d, %H:%M:%S')#.date()
		txn.date = date

		txn.amount = abs(self.to_number(item['Amount']))
		assert txn.amount >= 0, f'Negative fee: {item}'
		txn.unit = item['Currency']

		symbol = self.sanitize_symbol(item['Symbol'], item['Currency'])
		assert symbol is not None, f'Unknown symbol: {item}'

		assert 'tax' in item['Description'].lower(), f'No tax in description: {item}'

		txn.description = (f'{item["Description"]} for {item["Quantity"]} {symbol} '
						   f'@ {item["Trade Price"]} {item["Currency"]}')

		return txn

	def parse_interest(self, item: dict, tags: dict[str, list[Record]]):

		amt = self.to_number(item['Amount'])

		assert amt != 0, f'Zero interest: {item}'

		txn = Transaction()

		txn.sender = 'interest' if amt > 0 else self.account
		txn.receiver = self.account if amt > 0 else 'institution'

		txn.date = datetime.strptime(item['Date'], '%Y-%m-%d').date()

		txn.amount = abs(self.to_number(item['Amount']))
		txn.unit = item['Currency']

		txn.description = item['Description']

		return txn

	def parse_forex(self, item: dict, tags: dict[str, list[Record]]):

		proceeds = self.to_number(item['Proceeds'])
		currency = item['Currency']
		quantity = self.to_number(item['Quantity'])

		target, src = item['Symbol'].split('.')
		assert src == currency, f'{src} != {currency} ({target})'

		date = datetime.strptime(item['Date/Time'], '%Y-%m-%d, %H:%M:%S')#.date()

		txn = Transaction(sender=self.account, receiver=self.account)
		txn.date = date

		txn.description = f'rate: {item["T. Price"]} {target}/{src}'

		assert (proceeds > 0) != (quantity > 0), f'{proceeds} {quantity}'

		if proceeds > 0:
			txn.amount, txn.unit = abs(quantity), target
			txn.received_amount, txn.received_unit = abs(proceeds), src
		else:
			txn.amount, txn.unit = abs(proceeds), src
			txn.received_amount, txn.received_unit = abs(quantity), target

		if any(k.startswith('Comm in') for k in item):
			raw = [k for k in item if k.startswith('Comm in')]
			assert len(raw) == 1
			raw = raw[0]

			cost = abs(item[raw])
			if cost != 0:
				fee = Transaction()

				fee.sender = self.account
				fee.receiver = 'institution'

				fee.date = date

				fee.description = f'commission fee'

				fee.amount = abs(self.to_number(item[raw]))
				fee.unit = raw.split('Comm in ')[-1]

				return [txn, fee]
		return txn

	def parse_dividend(self, item: dict, tags: dict[str, list[Record]]):

		txn = Transaction()

		txn.sender = 'dividend'
		txn.receiver = self.account

		txn.date = datetime.strptime(item['Date'], '%Y-%m-%d').date()

		txn.amount = format_european_amount(item['Amount'])
		txn.unit = item['Currency']

		txn.description = item['Description']

		return txn

	def parse_transfer(self, item: dict, tags: dict[str, list[Record]]):

		amt = item['Amount']
		currency = item['Currency']

		txn = Transaction() if amt < 0 else Verification()

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
		# txn.location = ',online'

		return txn

	def sanitize_symbol(self, symbol: str, currency: str):
		if (symbol, currency) in self.symbols:
			return self.symbols[symbol, currency]
		if symbol.endswith('d') or symbol.endswith('e') or symbol.endswith('b'):
			return self.sanitize_symbol(symbol[:-1], currency)

	def parse_trade(self, item: dict, tags: dict[str, list[Record]]):

		txn = Transaction(sender=self.account, receiver=self.account)

		proceeds = self.to_number(item['Proceeds'])
		currency = item['Currency']

		quantity = self.to_number(item['Quantity'])
		raw_symbol = item['Symbol']
		symbol = self.sanitize_symbol(raw_symbol, currency)
		assert symbol is not None, f'Unknown symbol: {raw_symbol} ({currency})'

		txn.date = datetime.strptime(item['Date/Time'], '%Y-%m-%d, %H:%M:%S')#.date()

		gains = self.to_number(item['Realized P/L'])
		gain_info = f' (P/L: {gains} {currency})' if gains != 0 else ''
		txn.description = f'{self.to_number(item["T. Price"])} {currency}/{symbol}{gain_info}'

		if proceeds > 0:
			txn.amount, txn.unit = abs(quantity), symbol
			txn.received_amount, txn.received_unit = abs(proceeds), currency
		else:
			txn.amount, txn.unit = abs(proceeds), currency
			txn.received_amount, txn.received_unit = abs(quantity), symbol

		# cash.description = f'{"bought" if amt < 0 else "sold"} {quantity} share/s of {symbol}'

		cost = self.to_number(item['Comm/Fee'])
		if cost != 0:
			fee = Transaction()

			fee.amount = abs(cost)
			fee.unit = currency

			fee.sender = self.account
			fee.receiver = 'institution'

			fee.date = txn.date
			fee.description = 'commission/fee'

			return [txn, fee]
		return txn



@fig.component('fidelity')
class Fidelity(Parser):
	pass


