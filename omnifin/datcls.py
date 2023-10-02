import sqlite3
from datetime import datetime, date as datelike
from dateutil import parser
from dataclasses import dataclass



# class SimpleRecord:
# 	_table_name = None
# 	@classmethod
# 	def from_id(cls, cursor: sqlite3.Cursor, ID: int):
# 		table = cls._table_name
# 		if table is None:
# 			raise NotImplementedError("Table name not set.")
#
# 		cursor.execute(f'SELECT * FROM {table} WHERE id = ?', (ID,))
# 		return cls(*cursor.fetchone())



class Lazy:
	_loader_fn = None

	def __init__(self, *, _lazy_id=None, **kwargs):
		super().__init__(**kwargs)
		self._lazy_id = _lazy_id

	@classmethod
	def from_id(cls, ID: int):
		return cls(_lazy_id=ID)

	def _load(self):
		if self._loader_fn is None:
			raise NotImplementedError("Loader function not set.")
		raw: tuple = self._loader_fn(self._lazy_id)
		self.__dict__.update({k: v for k, v in zip(self.__annotations__, raw)})
		self._lazy_id = None

	def __getattr__(self, item):
		if item not in self.__getattribute__('__dict__') and item in self.__getattribute__('__annotations__'):
			self._load()
		return self.__getattribute__(item)

	def __loaded_str__(self):
		return super().__str__()

	def __loaded_repr__(self):
		return super().__repr__()

	def __str__(self):
		return self.__loaded_str__() if self._lazy_id is None else f'{self.__class__.__name__}({self._lazy_id})'

	def __repr__(self):
		return self.__loaded_repr__() if self._lazy_id is None else f'{self.__class__.__name__}({self._lazy_id})'



class Record:
	def __post_init__(self):
		for key, typ in self.__annotations__.items():
			if issubclass(typ, datelike):
				val = getattr(self, key)
				if isinstance(val, str):
					val = parser.parse(val)#.date()
					setattr(self, key, val)
			if issubclass(typ, Lazy):
				val = getattr(self, key)
				if isinstance(val, int):
					val = typ.from_id(val)
					setattr(self, key, val)



@dataclass
class Report(Lazy, Record):
	ID: int
	date: datelike
	category: str
	account: 'Account'
	description: str
	created: datelike

	def __loaded_str__(self):
		return f'{self.category}[{self.date.strftime("%Y-%m-%d")}]'

	def __loaded_repr__(self):
		return f'{self.__class__.__name__}({self.category}, {self.date.strftime("%Y-%m-%d")})'



@dataclass
class Asset(Lazy, Record):
	ID: int
	name: str
	category: str
	description: str
	report: Report

	def __loaded_str__(self):
		return self.name

	def __loaded_repr__(self):
		return f'{self.category}:{self.name}'



@dataclass
class Account(Lazy, Record):
	ID: int
	name: str
	account_type: str
	category: str
	description: str
	report: Report

	def __loaded_str__(self):
		return self.name

	def __loaded_repr__(self):
		if self.category is None:
			return self.name
		return f'{self.category}:{self.name}'



@dataclass
class Tag(Lazy, Record):
	ID: int
	name: str
	description: str
	report: Report

	def __loaded_str__(self):
		return f'<{self.name}>'

	def __loaded_repr__(self):
		return f'<{self.name}>'



@dataclass
class Statement(Lazy, Record):
	ID: int
	date: datelike
	account: Account
	balance: float
	unit: Asset
	description: str
	report: Report

	def __loaded_str__(self):
		return f'{self.balance} {self.unit} ({self.account})'

	def __loaded_repr__(self):
		return (f'{self.__class__.__name__}({self.balance} {self.unit}, '
				f'{self.account}, {self.date.strftime("%Y-%m-%d")}))')


@dataclass
class Transaction(Lazy, Record):
	ID: int
	date: datelike
	description: str
	amount: float
	unit: Asset
	sender: Account
	receiver: Account
	received_amount: float
	received_unit: Asset
	report: Report

	def __loaded_str__(self):
		if self.received_amount is None:
			return f'{self.amount} {self.unit} ({self.sender} -> {self.receiver})'
		return (f'{self.amount} {self.unit} ({self.sender}) '
				f'-> {self.received_amount} {self.received_unit} ({self.receiver})')

	def __loaded_repr__(self):
		return (f'{self.__class__.__name__}({self.amount} {self.unit} ({self.sender}), '
				f'{self.received_amount} {self.received_unit} ({self.receiver}), '
				f'{self.date.strftime("%Y-%m-%d")}))')


