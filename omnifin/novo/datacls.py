from .imports import *



@dataclass
class Record:
	ID: int = None


	@property
	def exists(self):
		return self.ID is not None


	def load(self):
		pass


	def write(self, conn):
		raise NotImplementedError



class AutoRecord(Record):
	_conn: sqlite3.Connection = None
	@classmethod
	def set_conn(cls, conn):
		cls._conn = conn


	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls._cache = {}


	_cache = None
	@classmethod
	def _find_record(self, query: str | int | Record):
		raise NotImplementedError
	@classmethod
	def find(cls, query: str | int | Record):
		return cls._cache.setdefault(query, cls._find_record(query))

	@classmethod
	def _find_from_ID(cls, ID):

		

		return cls._find_record(ID)



@dataclass
class Report(Record):
	category: str
	account: 'Account' = None
	description: str = None
	created: datelike

	@classmethod
	def _find_record(cls, query: str | int):
		return cls._conn.execute(f'SELECT * FROM reports WHERE ID={query}').fetchone()


@dataclass
class Asset(Record):
	name: str
	category: str
	description: str = None
	report: Report = None



@dataclass
class Tag(Record):
	name: str
	category: str = None
	description: str = None
	report: Report = None



@dataclass
class Account(Record):
	name: str
	category: str
	owner: str
	description: str = None
	report: Report = None



@dataclass
class Statement(Record):
	date: datelike
	account: Account
	balance: float
	unit: Asset
	description: str = None
	report: Report = None



@dataclass
class Transaction(Record):
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
	report: Report = None



@dataclass
class Verification(Record):
	txn: Transaction = None
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









