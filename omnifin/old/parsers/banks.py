
from omnibelt import save_txt, load_txt, save_json, load_json
from tabulate import tabulate
from tqdm import tqdm
from pathlib import Path
import omnifig as fig
import pandas as pd
from fuzzywuzzy import fuzz
from datetime import datetime
from dateutil import parser

from .. import misc
from ..scripts import get_manager, get_world, setup_report
from ..identification import World
from ..datcls import Report, Account, Transaction, Tag, Record, Verification
from ..parsing import Parser, Processor, ParseError



class American_Bank_Processor(Processor):
	def __init__(self, account: str, **kwargs):
		super().__init__(**kwargs)
		self.account = None
		self.account_name = account


	def prepare(self, w: World):
		super().prepare(w)
		self.account = w.find_account(self.account_name)
		self.cash = w.find_account('cash')
		self.usd = w.find_asset('USD')


	def format_amount(self, amount: str) -> float:
		amount = amount.replace(',','')
		amount = float(amount)
		return amount

	def format_mcc(self, mcc: str | int):
		if mcc is not None:
			mcc = str(mcc) if isinstance(mcc, int) else mcc
			return self.get_mcc_tag(mcc)



class BOA(American_Bank_Processor):
	def process(self, entry: dict):
		if entry['Amount'] is None:
			return

		da = datetime.strptime(entry['Date'], '%m/%d/%Y')

		loc = entry.get('Location')

		amount = self.format_amount(entry['Amount'])

		mcc = self.format_mcc(entry.get('MCC'))

		assert entry['Sender'] is not None ^ entry['Receiver'] is not None, f'Entry {entry} has no sender or receiver'
		if entry['Receiver'] is None:
			sender = self.w.find_account(entry['Sender'])
			receiver = self.account
		else:
			sender = self.account
			receiver = self.w.find_account(entry['Receiver'])

		desc = entry['Note']

		if (sender == self.account or sender.owner == 'external'):
			txn = Transaction(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.usd,
				receiver=receiver,
				description=desc,
			)
		else:
			txn = Verification(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.usd,
				receiver=receiver,
				description=desc,
			)

		if mcc is not None:
			txn.add_tag(mcc)
		return txn



class Heritage(American_Bank_Processor):
	def process(self, entry: dict):
		if entry['Amount'] is None:
			return

		da = datetime.strptime(entry['Date'], '%m-%d-%Y')

		loc = entry.get('Location')

		amount = self.format_amount(entry['Amount'])

		mcc = self.format_mcc(entry.get('MCC'))

		assert entry['Sender'] is not None ^ entry['Receiver'] is not None, f'Entry {entry} has no sender or receiver'
		if entry['Receiver'] is None:
			sender = self.w.find_account(entry['Sender'])
			receiver = self.account
		else:
			sender = self.account
			receiver = self.w.find_account(entry['Receiver'])

		desc = entry['Description']
		if entry['Note'] is not None:
			desc = f'{desc} - {entry["Note"]}'

		if (sender == self.account or sender.owner == 'external'):
			txn = Transaction(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.usd,
				receiver=receiver,
				description=desc,
			)
		else:
			txn = Verification(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.usd,
				receiver=receiver,
				description=desc,
			)

		if mcc is not None:
			txn.add_tag(mcc)
		return txn



class BECU(American_Bank_Processor):
	def process(self, entry: dict):
		if bool(entry['Debit']) == bool(entry['Credit']):
			return

		da = datetime.strptime(entry['Date'], '%m/%d/%Y')

		loc = entry.get('Location')

		amount = self.format_amount(entry['Amount'])

		mcc = self.format_mcc(entry.get('MCC'))

		assert bool(entry['Sender']) ^ bool(entry['Receiver']), f'Entry {entry} has no sender or receiver'
		if entry['Receiver']:
			sender = self.w.find_account(entry['Sender'])
			receiver = self.account
		else:
			sender = self.account
			receiver = self.w.find_account(entry['Receiver'])

		desc = entry['Note']
		if not desc:
			desc = None

		if (sender == self.account or sender.owner == 'external'):
			txn = Transaction(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.usd,
				receiver=receiver,
				description=desc,
			)
		else:
			txn = Verification(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.usd,
				receiver=receiver,
				description=desc,
			)

		if mcc is not None:
			txn.add_tag(mcc)
		return txn



class European_Bank_Processor(Processor):
	def __init__(self, account: str, **kwargs):
		super().__init__(**kwargs)
		self.account = None
		self.account_name = account


	def prepare(self, w: World):
		super().prepare(w)
		self.account = w.find_account(self.account_name)
		self.cash = w.find_account('cash')
		self.eur = w.find_asset('EUR')


	def format_amount(self, amount: str) -> float:
		amount = amount.replace(' ','').replace(',','.')
		amount = abs(float(amount))
		return amount


	def format_mcc(self, mcc: str | int):
		if mcc is not None:
			mcc = str(mcc) if isinstance(mcc, int) else mcc
			return self.get_mcc_tag(mcc)



class Bank99(European_Bank_Processor):
	def process(self, entry: dict):
		if not entry['Betrag']:
			return

		da = datetime.strptime(entry['Umsatzzeit'], '%Y-%m-%d-%H.%M.%S.%f')

		loc = entry.get('Location', 'Vienna,Austria')

		amount = self.format_amount(entry['Betrag'])

		mcc = self.format_mcc(entry.get('MCC'))

		assert entry['Sender'] is not None ^ entry['Receiver'] is not None, f'Entry {entry} has no sender or receiver'
		if entry['Receiver'] is None:
			sender = self.w.find_account(entry['Sender'])
			receiver = self.account
		else:
			sender = self.account
			receiver = self.w.find_account(entry['Receiver'])

		desc = entry['Notes']
		if desc is None or not len(desc):
			desc = None

		ref = entry.get('Eigene Referenz')

		if (sender == self.account or sender.owner == 'external'):
			txn = Transaction(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.eur,
				receiver=receiver,
				description=desc,
				reference=ref,
			)
		else:
			txn = Verification(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.eur,
				receiver=receiver,
				description=desc,
				reference=ref,
			)

		if mcc is not None:
			txn.add_tag(mcc)
		return txn



class Commerzbank(European_Bank_Processor):
	def extract_reference(self, text: str):
		if 'End-to-End-Ref.:' not in text:
			return

		head = text.split('End-to-End-Ref.: ')
		if not len(head):
			return
		head = head[-1].split(' Kundenreferenz:')
		if not len(head):
			return
		head = head[0]
		if not len(head) or 'notprovided' in head.lower():
			return
		return head


	def process(self, entry: dict):
		if not entry['Betrag']:
			return

		da = datetime.strptime(entry['Buchungstag'], '%d.%m.%Y')

		loc = entry.get('Location', 'Tuebingen,Germany')

		amount = self.format_amount(entry['Betrag'])

		mcc = self.format_mcc(entry.get('MCC'))

		assert entry['Sender'] is not None ^ entry['Receiver'] is not None, f'Entry {entry} has no sender or receiver'
		if entry['Receiver'] is None:
			sender = self.w.find_account(entry['Sender'])
			receiver = self.account
		else:
			sender = self.account
			receiver = self.w.find_account(entry['Receiver'])

		desc = entry['Note']
		if desc is None or not len(desc):
			desc = None

		ref = self.extract_reference(entry['Buchungstext'])

		if (sender == self.account or sender.owner == 'external'):
			txn = Transaction(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.eur,
				receiver=receiver,
				description=desc,
				reference=ref,
			)
		else:
			txn = Verification(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.eur,
				receiver=receiver,
				description=desc,
				reference=ref,
			)

		if mcc is not None:
			txn.add_tag(mcc)
		return txn



class DKB(European_Bank_Processor):
	def process(self, entry: dict):
		if not entry['Betrag'] or not entry['Status'] == 'Gebucht':
			return

		da = datetime.strptime(entry['Buchungsdatum'], '%d.%m.%y')

		loc = entry.get('Location', 'Tuebingen,Germany')

		amount = self.format_amount(entry['Betrag (€)'])

		mcc = self.format_mcc(entry.get('MCC'))

		assert entry['Sender'] is not None ^ entry['Receiver'] is not None, f'Entry {entry} has no sender or receiver'
		if entry['Receiver'] is None:
			sender = self.w.find_account(entry['Sender'])
			receiver = self.account
		else:
			sender = self.account
			receiver = self.w.find_account(entry['Receiver'])

		desc = entry['Verwendungszweck']
		if desc is None or not len(desc):
			desc = None

		ref = entry['Kundenreferenz']

		if (sender == self.account or sender.owner == 'external'):
			txn = Transaction(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.eur,
				receiver=receiver,
				description=desc,
				reference=ref,
			)
		else:
			txn = Verification(
				date=da,
				location=loc,
				sender=sender,
				amount=amount,
				unit=self.eur,
				receiver=receiver,
				description=desc,
				reference=ref,
			)

		if mcc is not None:
			txn.add_tag(mcc)
		return txn


