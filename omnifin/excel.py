from .imports import *

from .datacls import Transaction

def export_transactions(path: Path, txns: Iterable[Transaction]):

	rows = []
	tags = Counter()

	for txn in txns:
		mytags = list(txn.tags())
		mccs = [tag for tag in mytags if tag.category == 'MCC']
		assert len(mccs) <= 1, f'Multiple MCCs: {mccs}'

		mcc = None if not len(mccs) else mccs[0].name

		row = {
			'Verified': False,
			'Date': txn.date,
			'ID': txn.ID,
			'Location': txn.location,
			'Description': txn.description,
			'Reference': txn.reference,
			'Sender': txn.sender.name,
			'Amount': txn.amount,
			'Unit': txn.unit.name,
			'Receiver': txn.receiver.name,
			'RecAmount': txn.received_amount,
			'RecUnit': txn.received_unit if txn.received_unit is None else txn.received_unit.name,
			'MCC': mcc,
			'Tags': [f'{tag.category}:{tag.name}' for tag in mytags if tag.category != 'MCC'],
		}

		rows.append(row)
		tags.update(row['Tags'])

	for row in rows:
		row.update({tag: tag in row['Tags'] for tag, _ in tags.most_common()})
		del row['Tags']
	
	df = pd.DataFrame(rows)
	df.to_csv(path, index=False)
	return path








