from typing import Optional, Union, Type, TypeVar, Any, Callable, Iterable, Mapping, Sequence, Tuple, List, Dict
import sqlite3
import omnifig as fig
from .records import datelike, Figged, Record, Fillable, Tagged, Linked


# adds functions to read records
def init_loading(conn: sqlite3.Connection):
	def load_record(record: Record, table_name: str, primary_key: int) -> tuple:
		c = conn.cursor()
		c.execute(f'SELECT * FROM {table_name} WHERE id = ?', (primary_key,))
		return c.fetchone()
	Record._load_fn = load_record

	def load_tags(record: Record, table_name: str, primary_key: int) -> list['Tag']:
		c = conn.cursor()
		c.execute(f'SELECT tag_id FROM {table_name} WHERE transaction_id = ?', (primary_key,))
		return [Tag.from_key(tag_id) for tag_id, in c.fetchall()]
	Tagged._load_tags = load_tags

	def load_links(record: Record, table_name: str, primary_key: int) -> tuple:
		c = conn.cursor()
		c.execute(f'SELECT id1 FROM {table_name} WHERE id2 = ?', (primary_key,))
		links1 = [Transaction.from_key(edge) for edge, in c.fetchall()]
		c.execute(f'SELECT id2 FROM {table_name} WHERE id1 = ?', (primary_key,))
		links2 = [Transaction.from_key(edge) for edge, in c.fetchall()]
		return [*links1, *links2]
	Linked._load_links = load_links

	def find_rows(record: Record, table_name: str, props) -> list[tuple]:
		c = conn.cursor()
		query = f'SELECT * FROM {table_name}'
		props = {k: v for k, v in props.items() if v is not None}
		if len(props) > 0:
			query += ' WHERE '
			query += ' AND '.join(f'{k} = ?' for k in props)
		c.execute(query, tuple(props.values()))
		return c.fetchall()
	Fillable._fill_fn = find_rows



@fig.component('report')
class Report(Fillable, Figged, table='reports'):
	ID: int = None
	category: str
	account: 'Account' = None
	description: str = None
	created: datelike

	def __loaded_str__(self):
		return f'{self.category}[{self.created.strftime("%y-%m-%d %H:%M:%S")}]'

	def __loaded_repr__(self):
		return f'{self.__class__.__name__}({self.category}, {self.created.strftime("%y-%m-%d %H:%M:%S")})'

	def export_row(self):
		return [self.category, self.account, self.description]



@fig.component('asset')
class Asset(Fillable, Figged, table='assets'):
	ID: int = None
	name: str
	category: str
	description: str = None
	report: Report

	def __loaded_str__(self):
		return self.name

	def __loaded_repr__(self):
		return f'<{self.category}:{self.name}>'

	def shortcuts(self):
		yield self.name
		yield f'{self.category}:{self.name}'



@fig.component('tag')
class Tag(Fillable, Figged, table='tags'):
	ID: int = None
	name: str
	category: str = None
	description: str = None
	report: Report

	def __loaded_str__(self):
		return f'<TAG:{self.name}>'

	def __loaded_repr__(self):
		return f'<TAG:{self.name}>'

	def shortcuts(self):
		yield self.name
		yield f'<{self.name}>'
		yield f'TAG:{self.name}'



@fig.component('account')
class Account(Tagged, Figged, table='accounts'):
	ID: int = None
	name: str
	category: str
	owner: str
	description: str = None
	report: Report

	@property
	def tags_table_name(self):
		return 'account_tags'

	def __loaded_str__(self):
		return self.name

	def __loaded_repr__(self):
		if self.category is None:
			return f'<{self.name}>'
		return f'<{self.category}:{self.name}>'

	def shortcuts(self):
		yield self.name
		yield f'{self.category}:{self.name}'



@fig.component('statement')
class Statement(Tagged, Linked, Figged, table='statements'):
	ID: int = None
	date: datelike
	account: Account
	balance: float
	unit: Asset
	description: str = None
	report: Report

	@property
	def tags_table_name(self):
		return 'statement_tags'
	@property
	def links_table_name(self):
		return 'statement_links'

	def __loaded_str__(self):
		return f'{self.account}[{self.date.strftime("%y-%m-%d")}] {self.balance} {self.unit}'

	def __loaded_repr__(self):
		return f'<{self.account}, {self.balance} {self.unit}, {self.date.strftime("%y-%m-%d")}>'



@fig.component('transaction')
class Transaction(Tagged, Linked, Figged, table='transactions'):
	ID: int = None
	date: datelike
	location: str = None
	sender: Account
	amount: float
	unit: Asset
	receiver: Account
	received_amount: float = None
	received_unit: Asset = None
	description: str = None
	reference: str = None
	report: Report

	@property
	def tags_table_name(self):
		return 'transaction_tags'
	@property
	def links_table_name(self):
		return 'transaction_links'

	def __loaded_str__(self):
		if self.received_amount is None:
			return f'{self.sender} {self.amount} {self.unit} -> {self.receiver}'
		return f'{self.sender} {self.amount} {self.unit} -> {self.receiver} {self.received_amount} {self.received_unit}'

	def __loaded_repr__(self):
		if self.received_amount is None:
			return f'<{self.sender} -> {self.receiver}, {self.amount} {self.unit}, {self.date.strftime("%y-%m-%d")}>'
		return (f'<{self.sender} -> {self.receiver}, '
				f'{self.amount} {self.unit} -> {self.received_amount} {self.received_unit}, '
				f'{self.date.strftime("%y-%m-%d")}>')


