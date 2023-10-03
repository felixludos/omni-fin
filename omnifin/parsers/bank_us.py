import omnifig as fig

from ..parsing import Parser


@fig.component('parser/usbank')
class USBank(Parser):
	def __init__(self, skip_credit=True):
		self.skip_credit = skip_credit


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
		if self.skip_credit and info['Transaction'] == 'CREDIT':
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




