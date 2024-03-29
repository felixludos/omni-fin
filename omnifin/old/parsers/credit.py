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
from ..datcls import Report, Account, Transaction, Tag, Record
from ..parsing import Parser, Processor, ParseError



@fig.component('parser/usbank')
class USBank_Credit_Card(Parser):
	def __init__(self, save_location_prompt=True, skip_payments=True):
		self.save_location_prompt = save_location_prompt
		self.skip_payments = skip_payments
		if not skip_payments:
			raise NotImplementedError


	@staticmethod
	def extract_currency(info: dict, raw: str):
		terms = raw.strip().split(' - ')
		if len(terms) == 1:
			return

		name, rec = ' - '.join(terms[:-1]), terms[-1].strip()
		words = rec.split()

		amt, curr = words[0], ' '.join(words[1:])
		try:
			amt = float(amt)
		except ValueError:
			return

		info['cleaned'] = name
		info['received-amount'] = amt
		info['received-unit'] = curr


	def parse(self, info: dict) -> dict | None:
		if self.skip_payments and info['Transaction'] == 'CREDIT':
			return

		info['usd'] = abs(info['Amount'])

		terms = info['Memo'].strip().split(';')
		terms = [t.strip() for t in terms]
		assert len(terms) == 6, f"Expected 6 terms, got {len(terms)}: {terms}"

		if len(terms[0]):
			info['txn-number'] = terms[0]
		if len(terms[1]) == 5:
			info['mcc'] = terms[1]

		if any(t for t in terms[2:]):
			info['extra-info'] = ';'.join(terms[2:])

		self.extract_currency(info, info['Name'])

		info['original'] = info['Name']
		info['date'] = info['Date']

		del info['Name'], info['Memo'], info['Amount'], info['Transaction'], info['Date']
		return info


	_template = '''Extract location information from each of these descriptions in exactly the given format.

Input:
"RYANAIR  WLKKSA0       K67E6R0       IE"
"TST* Voodoo Doughnut O Portland      OR"
"TRADER JOE'S #140  QPS REDMOND       WA"
"IMART ORIENTAL WESTEND GLASGOW GB"
"PAYPAL *DBVERTRIEBG    35314369001   DE"
"WASTE MGMT WM EZPAY    866-834-2080  TX"
"HAARDT & KRUEGER WIEN AT"
"APOTHEKE ZUM HEILIGEN WIEN AT"
"VOGLIA DI PIZZA ROMA IT"
"RESTAURANT FISCHERBRAE WIEN AT"
"Food Lab s.r.o. Bratislava - SK"
"SICHUANESE CUISINE     REDMOND       WA"
"76 - ICICLE QUICK STOP LEAVENWORTH   WA"
"INTUIT *TURBOTAX       CL.INTUIT.COM CA"
"GRUEN BERLIN GMBH BERLIN DE"
"TueBus - Stadtverkehr Tuebingen DE"
"DEICHMANN Wien-Favorit Wien-Favorite AT"
"GELATO ITALIANO ROMA IT"
"APOTHEKE ZUM HEILIGEN WIEN AT"
"PAYPAL *MINT MOBILE    402-935-7733  CA"
"SQ *JOEY BELLEVUE      Bellevue      WA"
"LA STAGIONI ORTOFRUTTA BELLANO IT"
"ATT* BILL PAYMENT      800-331-0500  TX"
"PCC - REDMOND          REDMOND       WA"
"www.anyvan.com INTERNET GB"
"KLM AIRLI0742432072847 WASHINGTON DC "
"Istanbul Restaurant Ac Tuebingen DE"
"TST* JAMBA JUICE"
"AMZN Mktp DE*2S3BF51K5 800-279-6620 LU"
Output:
"RYANAIR  WLKKSA0       K67E6R0       IE","","Ireland","online"
"TST* Voodoo Doughnut O Portland      OR","Portland","Oregon","inperson"
"TRADER JOE'S #140  QPS REDMOND       WA","Redmond","Washington","inperson"
"IMART ORIENTAL WESTEND GLASGOW GB","Glasgow","Great Britain","inperson"
"PAYPAL *DBVERTRIEBG    35314369001   DE","","Germany","online"
"WASTE MGMT WM EZPAY    866-834-2080  TX","","Texas","online"
"HAARDT & KRUEGER WIEN AT","Vienna","Austria","inperson"
"APOTHEKE ZUM HEILIGEN WIEN AT","Vienna","Austria","inperson"
"VOGLIA DI PIZZA ROMA IT","Rome","Italy","inperson"
"RESTAURANT FISCHERBRAE WIEN AT","Vienna","Austria","inperson"
"Food Lab s.r.o. Bratislava - SK","Bratislava","Slovakia","inperson"
"SICHUANESE CUISINE     REDMOND       WA","Redmond","Washington","inperson"
"76 - ICICLE QUICK STOP LEAVENWORTH   WA","Leavenworth","Washington","inperson"
"INTUIT *TURBOTAX       CL.INTUIT.COM CA","","California","online"
"GRUEN BERLIN GMBH BERLIN DE","Berlin","Germany","inperson"
"TueBus - Stadtverkehr Tuebingen DE","Tuebingen","Germany","inperson"
"DEICHMANN Wien-Favorit Wien-Favorite AT","Vienna","Austria","inperson"
"GELATO ITALIANO ROMA IT","Rome","Italy","inperson"
"APOTHEKE ZUM HEILIGEN WIEN AT","Vienna", "Austria","inperson"
"PAYPAL *MINT MOBILE    402-935-7733  CA","","California","online"
"SQ *JOEY BELLEVUE      Bellevue      WA","Bellevue","Washington","inperson"
"LA STAGIONI ORTOFRUTTA BELLANO IT","Bellano","Italy","inperson"
"ATT* BILL PAYMENT      800-331-0500  TX","","Texas","online"
"PCC - REDMOND          REDMOND       WA","Redmond","Washington","inperson"
"www.anyvan.com INTERNET GB","","Great Britain","online"
"KLM AIRLI0742432072847 WASHINGTON DC ","Washington","DC","online"
"Istanbul Restaurant Ac Tuebingen DE","Tuebingen","Germany","inperson"
"TST* JAMBA JUICE","","","inperson"
"AMZN Mktp DE*2S3BF51K5 800-279-6620 LU","","Luxembourg","online"

Input:
{prompts}
Output:'''
	def cleanup(self, outpath, entries):
		if self.save_location_prompt:
			path = outpath.parent / f'{outpath.stem}-loc-prompt.txt'

			prompts = set(entry.get('cleaned', entry.get('original')) for entry in entries)

			full = self._template.format(
				# prompts='\n'.join(f'{i+1}. "{p}"' for i,p in enumerate(prompts)),
				prompts='\n'.join(f'"{p}"' for i,p in enumerate(prompts)),
			)

			save_txt(full, path)
			print(f'Saved prompt for extracting locations of {len(prompts)} to {path}')



@fig.script('usbank-locs', description='Include location information for parsed US Bank transactions.')
def usbank_locs(cfg: fig.Configuration):
	path = misc.get_path(cfg, path_key='path', root_key='root')
	if not path.exists():
		raise FileNotFoundError(f'File {path} not found.')

	locpath = misc.get_path(cfg, path_key='loc-path', root_key='root')
	if not locpath.exists():
		raise FileNotFoundError(f'File {locpath} not found.')

	overwrite = cfg.pull('overwrite', False)

	entries = load_json(path)
	todo = [entry for entry in entries if overwrite or 'location' not in entry]
	cfg.print(f'Loaded {len(todo)} todo (from {len(entries)} entries) from {path}')
	if not len(todo):
		cfg.print('Nothing to do.')

	df = pd.read_csv(locpath)
	cfg.print(f'Loaded {len(df)} locations from {locpath}')

	solutions = [row.to_dict() for _, row in df.iterrows()]
	options = {' '.join(w.strip() for w in sol['Details'].split()): sol for sol in solutions}
	keys = list(options.keys())

	itr = iter(todo)
	pbar = cfg.pull('pbar', True, silent=True)
	if pbar:
		itr = tqdm(itr, total=len(todo))

	perfect = 0
	failed = []
	for entry in itr:
		itr.set_description(f'matches={perfect}, failed={len(failed)}')

		key = entry.get('cleaned', entry.get('original')).strip()
		key = ' '.join(w.strip() for w in key.split())
		assert key is not None, f'Expected "cleaned" or "original" in entry, got {entry}'
		if key in options:
			perfect += 1
			loc = options[key]
			entry['city'] = loc['City'] if isinstance(loc['City'], str) else None
			entry['location'] = loc['Country'] if isinstance(loc['Country'], str) else None
			entry['online'] = loc['Type'] == 'online'

		else:
			best = max(keys, key=lambda k: fuzz.ratio(k, key))
			score = fuzz.ratio(best, key)
			if score < 98:
				failed.append(entry)
			else:
				loc = options[best]
				entry['match'] = loc['Details']
				entry['match-score'] = score
				entry['city'] = loc['City'] if isinstance(loc['City'], str) else None
				entry['location'] = loc['Country'] if isinstance(loc['Country'], str) else None
				entry['online'] = loc['Type'] == 'online'

	cfg.print(f'Found {perfect} perfect matches, {len(failed)} entries failed.')

	if len(failed) and cfg.pull('save-failed', True):
		save_json(failed, path.parent / f'{path.stem}-failed-locs.json')
		cfg.print(f'Saved failed entries to {path.parent / f"{path.stem}-failed-locs.json"}')

	save_json(entries, path)
	cfg.print(f'Saved updated entries to {path}')

	return entries, failed



@fig.component('parser/costco')
class Costco_Credit_Card(Parser):
	def __init__(self, save_location_prompt=True, skip_payments=True):
		self.save_location_prompt = save_location_prompt
		self.skip_payments = skip_payments
		if not skip_payments:
			raise NotImplementedError


	def parse(self, info: dict) -> dict | None:
		if self.skip_payments and (info['Debit'] is None or info['Debit'] != info['Debit']):
			return

		info['usd'] = abs(info['Debit'])

		assert info['Status'] == 'Cleared', f'Expected cleared status, got {info["Status"]!r}'
		info['original'] = info['Description']
		info['owner'] = info['Member Name']
		info['date'] = info['Date']

		del info['Status'], info['Date'], info['Debit'], info['Credit'], info['Member Name'], info['Description']
		return info


	_template = '''Extract information from each of these descriptions in exactly the given format:

original,MCC,merchant,city,state,online

Input:
"WWW.1AND1.COM CHESTERBROOK PA"
"QFC #5860 REDMOND WA"
"TST* Oasis Tea Zone - ChiSeattle WA"
"WWW COSTCO COM 800-955-2292 WA"
"QFC #5820 REDMOND WA"
"SPIRIT AIRL 4870357674242800-7727117 FLNAME:  DEPART:"
"SQ *TAPIOCA EXPRESS- REDMRedmond WA"
"LATE FEE - FEB PAYMENT PAST DUE"
"Netflix 1 8445052993 CA"
"IKEA SEATLE RENTON WA"
Output:
"WWW.1AND1.COM CHESTERBROOK PA","4816","WWW.1AND1.COM","Chesterbrook","Pennsylvania","online"
"QFC #5860 REDMOND WA","5411","QFC #5860","Redmond","Washington","inperson"
"TST* Oasis Tea Zone - ChiSeattle WA","5814","TST* Oasis Tea Zone - Chi","Seattle","Washington","inperson"
"WWW COSTCO COM 800-955-2292 WA","5310","WWW COSTCO COM","","Washington","online"
"QFC #5820 REDMOND WA","5411","QFC #5820","Redmond","Washington","inperson"
"SPIRIT AIRL 4870357674242800-7727117 FLNAME:  DEPART:","3003","SPIRIT AIRL","","","online"
"SQ *TAPIOCA EXPRESS- REDMRedmond WA","5814","SQ *TAPIOCA EXPRESS- REDM","Redmond","Washington","inperson"
"LATE FEE - FEB PAYMENT PAST DUE","6012","LATE FEE - FEB PAYMENT PAST DUE","","","online"
"Netflix 1 8445052993 CA","4899","Netflix","","California","online"
"IKEA SEATLE RENTON WA","5712","IKEA SEATLE","Renton","Washington","inperson"

Input:
{prompts}
Output:'''
	def cleanup(self, outpath, entries):
		if self.save_location_prompt:
			path = outpath.parent / f'{outpath.stem}-loc-prompt.txt'

			prompts = set(entry.get('original') for entry in entries)

			full = self._template.format(
				# prompts='\n'.join(f'{i+1}. "{p}"' for i,p in enumerate(prompts)),
				prompts='\n'.join(f'"{p}"' for i,p in enumerate(prompts)),
			)

			save_txt(full, path)
			print(f'Saved prompt for extracting locations of {len(prompts)} to {path}')



@fig.script('costco-locs',
			description='Include location and merchant information for Costco Credit Card transactions.')
def costco_locs(cfg: fig.Configuration):
	path = misc.get_path(cfg, path_key='path', root_key='root')
	if not path.exists():
		raise FileNotFoundError(f'File {path} not found.')

	locpath = misc.get_path(cfg, path_key='loc-path', root_key='root')
	if not locpath.exists():
		raise FileNotFoundError(f'File {locpath} not found.')

	overwrite = cfg.pull('overwrite', False)

	entries = load_json(path)
	todo = [entry for entry in entries if overwrite or 'location' not in entry]
	cfg.print(f'Loaded {len(todo)} todo (from {len(entries)} entries) from {path}')
	if not len(todo):
		cfg.print('Nothing to do.')

	df = pd.read_csv(locpath)
	cfg.print(f'Loaded {len(df)} locations from {locpath}')

	solutions = [row.to_dict() for _, row in df.iterrows()]
	options = {' '.join(w.strip() for w in sol['Raw'].split()): sol for sol in solutions}
	keys = list(options.keys())

	itr = iter(todo)
	pbar = cfg.pull('pbar', True, silent=True)
	if pbar:
		itr = tqdm(itr, total=len(todo))

	perfect = 0
	failed = []
	for entry in itr:
		itr.set_description(f'matches={perfect}, failed={len(failed)}')

		key = entry.get('cleaned', entry.get('original')).strip()
		key = ' '.join(w.strip() for w in key.split())
		assert key is not None, f'Expected "cleaned" or "original" in entry, got {entry}'
		if key in options:
			perfect += 1
			loc = options[key]
			entry['city'] = loc['City'] if isinstance(loc['City'], str) else None
			entry['location'] = loc['State'] if isinstance(loc['State'], str) else None
			entry['online'] = loc['Type'] == 'online'
			entry['merchant'] = loc['Merchant'] if isinstance(loc['Merchant'], str) else None
			entry['mcc'] = loc['MCC']

		else:
			best = max(keys, key=lambda k: fuzz.ratio(k, key))
			score = fuzz.ratio(best, key)
			if score < 98:
				failed.append(entry)
			else:
				loc = options[best]
				entry['match'] = loc['Details']
				entry['match-score'] = score
				entry['city'] = loc['City'] if isinstance(loc['City'], str) else None
				entry['location'] = loc['State'] if isinstance(loc['State'], str) else None
				entry['online'] = loc['Type'] == 'online'
				entry['merchant'] = loc['Merchant'] if isinstance(loc['Merchant'], str) else None
				entry['mcc'] = loc['MCC']

	cfg.print(f'Found {perfect} perfect matches, {len(failed)} entries failed.')

	if len(failed) and cfg.pull('save-failed', True):
		save_json(failed, path.parent / f'{path.stem}-failed-locs.json')
		cfg.print(f'Saved failed entries to {path.parent / f"{path.stem}-failed-locs.json"}')

	save_json(entries, path)
	cfg.print(f'Saved updated entries to {path}')

	return entries, failed



@fig.component('parser/amazon')
class Amazon_Parser(Parser):
	def __init__(self, include_missing_properties=True, skip_payments=True):
		self.include_missing_properties = include_missing_properties
		self.skip_payments = skip_payments
		if not skip_payments:
			raise NotImplementedError


	def parse(self, info: dict) -> dict | None:
		if self.skip_payments and info['Type'] == 'Payment':
			return

		info['usd'] = abs(info['Amount'])

		desc = info['Description']

		if desc.lower().startswith('amazon.com'):
			info['merchant'] = 'Amazon'
			info['reference'] = desc.split('*')[1].strip()
			info['location'] = 'United States'
			info['online'] = True
		elif (desc.lower().startswith('amzn mktp') or desc.lower().startswith('amznmktplace')
		      or desc.lower().startswith('amazon tips')):
			# may include Returns (info['Type'] == 'Return')
			terms = desc.split('*')
			if len(terms) == 2:
				head, ref = terms
				ref = ref.split(' ')[0].strip()
			else:
				head = terms[0]
				ref = None
			info['reference'] = ref
			info['location'] = 'Germany' if head.endswith('DE') else 'United States'
			info['online'] = True
		elif desc.lower().startswith('amazon prime'):
			info['merchant'] = 'Amazon'
			info['reference'] = desc.split('*')[1].strip()
			info['location'] = 'United States'
			info['online'] = True
		elif desc.startswith('WHOLEFDS'):
			info['merchant'] = 'Whole Foods'
			if 'RMD' in desc:
				info['location'] = 'Redmond,Washington'
			elif self.include_missing_properties:
				info['location'] = '[MISSING]'
			info['online'] = False
		else:
			print(f'\nFailed on: {desc!r}')
			# raise ParseError(f'Unknown description: {desc}')
			if self.include_missing_properties:
				info['merchant'] = '[MISSING]'
				info['location'] = '[MISSING]'
				info['online'] = '[MISSING]'

		info['original'] = info['Description']
		info['type'] = info['Type']
		info['category'] = info['Category']
		info['date'] = info['Transaction Date']
		info['posted-date'] = info['Post Date']

		del info['Memo'], info['Description'], info['Type'], info['Category'], info['Transaction Date'], info['Post Date'], info['Amount']
		return info



# Processor



@fig.component('processor/usbank')
class USBank_Card_Proc(Processor):
	def __init__(self, account: str, **kwargs):
		super().__init__(**kwargs)
		self.account_name = account


	def prepare(self, w: World):
		self.sender = w.find_account(self.account_name)
		self.receiver = w.find_account('merchant')
		super().prepare(w)


	def process(self, entry: dict):
		da = entry['date']

		city, loc, online = entry.get('city'), entry.get('location'), entry.get('online', False)
		if city is not None or loc is not None:
			loc = misc.format_location(city=city, location=loc, cat='online' if online else '')

		ref = entry.get('txn-number')

		mcc = entry.get('mcc')
		if mcc is not None and len(mcc) == 5:
			code = mcc[1:]
			mcc = self.get_mcc_tag(code)

		amount = entry['usd']
		unit = self.w.find_asset('usd')

		rec_amt = entry.get('received-amount')
		rec_unit = None
		if rec_amt is not None:
			rec_unit = self.w.find_asset(entry['received-unit'])

		txn = Transaction(
			date=da,
			location=loc,
			sender=self.sender,
			amount=amount,
			unit=unit,
			receiver=self.receiver,
			received_amount=rec_amt,
			received_unit=rec_unit,
			description=entry.get('cleaned', entry.get('original')),
			reference=ref,
		)
		if Transaction(date=da, reference=ref,
					   sender=self.sender, receiver=self.receiver,
					   amount=amount, unit=unit).in_db():
			return None
		if isinstance(mcc, Tag):
			txn.add_tag(mcc)

		return txn



@fig.component('processor/costco')
class Costco_Card_Proc(Processor):
	def __init__(self, account: str, **kwargs): # costco-gu, costco-ma
		super().__init__(**kwargs)
		self.account_name = account


	def prepare(self, w: World):
		self.w = w
		self.sender = w.find_account(self.account_name)
		self.receiver = w.find_account('merchant')
		super().prepare(w)


	def process(self, entry: dict):
		da = entry['date']
		da = datetime.strptime(da, '%m/%d/%Y')

		city, loc, online = entry.get('city'), entry.get('location'), entry.get('online', False)
		if city is not None or loc is not None:
			loc = misc.format_location(city=city, location=loc, cat='online' if online else '')

		mcc = entry.get('mcc')
		if mcc is not None and len(mcc) == 5:
			code = mcc[1:]
			mcc = self.get_mcc_tag(code)

		amount = entry['usd']
		unit = self.w.find_asset('usd')

		rec_amt = entry.get('received-amount')
		rec_unit = None
		if rec_amt is not None:
			rec_unit = self.w.find_asset(entry['received-unit'])

		txn = Transaction(
			date=da,
			location=loc,
			sender=self.sender,
			amount=amount,
			unit=unit,
			receiver=self.receiver,
			received_amount=rec_amt,
			received_unit=rec_unit,
			description=entry.get('cleaned', entry.get('original')),
			# reference=ref,
		)
		if Transaction(date=da, #reference=ref,
					   sender=self.sender, receiver=self.receiver,
					   amount=amount, unit=unit).in_db():
			return None
		if isinstance(mcc, Tag):
			txn.add_tag(mcc)

		return txn



@fig.component('processor/capitalone')
class Capitalone_Proc(Processor):
	def prepare(self, w: World):
		self.w = w
		self.sender = w.find_account('capitalone')
		self.receiver = w.find_account('merchant')
		super().prepare(w)


	def process(self, entry: dict):
		assert entry['Card No.'] == 3227, f'Expected card number 3227, got {entry["Card No."]}'
		if entry['Credit'] is not None:
			return

		da = entry['Transaction Date']
		da = datetime.strptime(da, '%Y-%m-%d')
		# da = parser.parse(da)

		city, loc, online = entry.get('City'), entry.get('State'), entry.get('Online', False)
		if city is not None or loc is not None:
			loc = misc.format_location(city=city, location=loc, cat='online' if online else '')

		ref = entry.get('Reference')

		mcc = entry.get('MCC')
		if mcc is not None and isinstance(mcc, int):
			mcc = self.get_mcc_tag(str(mcc))

		amount = entry['Debit']
		unit = self.w.find_asset('usd')

		desc = f'{entry["Description"]}|{entry["Category"]}'

		txn = Transaction(
			date=da,
			location=loc,
			sender=self.sender,
			amount=amount,
			unit=unit,
			receiver=self.receiver,
			description=desc,
			reference=ref,
		)
		if Transaction(date=da, reference=ref,
					   sender=self.sender, receiver=self.receiver,
					   amount=amount, unit=unit).in_db():
			return None
		if isinstance(mcc, Tag):
			txn.add_tag(mcc)

		return txn



@fig.component('processor/amazon')
class Amazon_Proc(Processor):
	def prepare(self, w: World):
		self.w = w
		self.sender = w.find_account('amazon')
		self.receiver = w.find_account('merchant')
		super().prepare(w)


	def process(self, entry: dict):
		da = entry['date']
		da = datetime.strptime(da, '%m/%d/%Y')
		# da = parser.parse(da)

		loc = entry['location']
		online = entry.get('online', False)

		terms = loc.split(',')
		if len(terms) == 2:
			city, loc = terms
		else:
			city = None
			loc = terms[0]
		if city is not None or loc is not None:
			loc = misc.format_location(city=city, location=loc, cat='online' if online else '')

		ref = entry.get('reference')

		mcc = entry.get('mcc')
		if mcc is not None and isinstance(mcc, int):
			mcc = self.get_mcc_tag(str(mcc))

		amount = entry['usd']
		unit = self.w.find_asset('usd')

		desc = f'{entry["original"]}|{entry["category"]}'

		txn = Transaction(
			date=da,
			location=loc,
			sender=self.sender,
			amount=amount,
			unit=unit,
			receiver=self.receiver,
			description=desc,
			reference=ref,
		)
		if Transaction(date=da, reference=ref,
					   sender=self.sender, receiver=self.receiver,
					   amount=amount, unit=unit).in_db():
			return None
		if isinstance(mcc, Tag):
			txn.add_tag(mcc)

		return txn



