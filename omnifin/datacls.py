from .imports import *



@dataclass
class RecordBase:
	ID: int = None


	@property
	def exists(self):
		return self.ID is not None


	def load(self):
		pass


	def write(self, conn):
		raise NotImplementedError



class Record(RecordBase):
	_conn: sqlite3.Connection = None
	@classmethod
	def set_conn(cls, conn):
		cls._conn = conn

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls._cache = {}

	# def __new__(cls, *args, **kwargs):
	# 	if cls._conn is not None:
	# 		return cls.find(*args, **kwargs)
	# 	return super().__new__(cls)

	# @classmethod
	# def _find_from_ID(cls, ID):
	# 	return cls._find_record(ID)

	@classmethod
	def clear_cache(cls):
		cls._cache.clear()


	_cache = None
	@classmethod
	def _find_record(self, query: str | int | 'Record', **props):
		raise NotImplementedError
	@classmethod
	def find(cls, query: str | int | 'Record', **props):
		if query is None and len(props) == 0:
			return None
		return cls._cache.setdefault(query, cls._find_record(query, **props))
	@classmethod
	def find_all(cls, **props):
		raise NotImplementedError



@dataclass
class Report(Record):
	category: str
	account: 'Account' = None
	description: str = None
	created: datelike


	@classmethod
	def _find_record(cls, query: int):
		assert isinstance(query, int), f'Invalid query: {query!r}'
		out = cls._conn.execute(f'SELECT * FROM reports WHERE id = ?', (query,)).fetchone()
		ID, category, account, description, created = out
		assert query == ID, f'Expected ID {query}, got {ID}'
		# account = Account.find(account)
		return cls(ID, category, account, description, created)


	def write(self, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = 'INSERT INTO reports (category, associated_account, description) VALUES (?, ?, ?)'
		conn.execute(cmd, (self.category, self.account.ID if self.account else None, self.description))
		return conn.cursor().lastrowid


@dataclass
class Asset(Record):
	name: str
	category: str
	description: str = None
	report: Report = None


	@classmethod
	def _find_record(cls, query: str | int):
		out = cls._conn.execute(f'SELECT * FROM assets WHERE {"id" if isinstance(query, int) else "name"} = ?',
								(query,)).fetchone()
		ID, name, category, description, report = out
		# report = Report.find(report)
		return cls(ID, name, category, description, report)


	def write(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = 'INSERT INTO assets (asset_name, asset_type, description, report) VALUES (?, ?, ?, ?)'
		conn.execute(cmd, (self.name, self.category, self.description, report.ID))
		return conn.cursor().lastrowid


	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = 'UPDATE assets SET asset_name = ?, asset_type = ?, description = ?, report = ? WHERE id = ?'
		conn.execute(cmd, (self.name, self.category, self.description, report.ID, self.ID))
		return self.ID


@dataclass
class Tag(Record):
	name: str
	category: str = None
	description: str = None
	report: Report = None


	@classmethod
	def _find_record(cls, query: str | int):
		out = cls._conn.execute(f'SELECT * FROM tags WHERE {"id" if isinstance(query, int) else "name"} = ?',
								(query,)).fetchone()
		ID, name, category, description, report = out
		# report = Report.find(report)
		return cls(ID, name, category, description, report)


	def write(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = 'INSERT INTO tags (tag_name, category, description, report) VALUES (?, ?, ?, ?)'
		conn.execute(cmd, (self.name, self.category, self.description, report.ID))
		return conn.cursor().lastrowid


	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = 'UPDATE tags SET tag_name = ?, category = ?, description = ?, report = ? WHERE id = ?'
		conn.execute(cmd, (self.name, self.category, self.description, report.ID, self.ID))
		return self.ID


@dataclass
class Account(Record):
	name: str
	category: str
	owner: str
	description: str = None
	report: Report = None


	@classmethod
	def _find_record(cls, query: str | int):
		out = cls._conn.execute(f'SELECT * FROM accounts WHERE {"id" if isinstance(query, int) else "name"} = ?',
								(query,)).fetchone()
		ID, name, category, owner, description, report = out
		# report = Report.find(report)
		return cls(ID, name, category, owner, description, report)


	def write(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = ('INSERT INTO accounts (account_name, account_type, account_owner, description, report) '
			   'VALUES (?, ?, ?, ?, ?)')
		conn.execute(cmd, (self.name, self.category, self.owner, self.description, report.ID))
		return conn.cursor().lastrowid


	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = ('UPDATE accounts SET account_name = ?, account_type = ?, account_owner = ?, description = ?, report = ? '
			   'WHERE id = ?')
		conn.execute(cmd, (self.name, self.category, self.owner, self.description, report.ID, self.ID))
		return self.ID


@dataclass
class Statement(Record):
	date: datelike
	account: Account
	balance: float
	unit: Asset
	description: str = None
	report: Report = None


	@classmethod
	def _find_record(cls, query: int):
		assert isinstance(query, int), f'Invalid query: {query!r}'
		out = cls._conn.execute(f'SELECT * FROM statements WHERE id = ?', (query,)).fetchone()
		ID, date, account, balance, unit, description, report = out
		assert query == ID, f'Expected ID {query}, got {ID}'
		# account = Account.find(account)
		# unit = Asset.find(unit)
		# report = Report.find(report)
		return cls(ID, date, account, balance, unit, description, report)


	def write(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = ('INSERT INTO statements (dateof, account, balance, unit, description, report) '
			   'VALUES (?, ?, ?, ?, ?, ?)')
		conn.execute(cmd, (self.date, self.account.ID, self.balance, self.unit.ID, self.description,
						   report.ID))
		return conn.cursor().lastrowid


	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = ('UPDATE statements SET dateof = ?, account = ?, balance = ?, unit = ?, description = ?, report = ? '
			   'WHERE id = ?')
		conn.execute(cmd, (self.date, self.account.ID, self.balance, self.unit.ID, self.description, report.ID, self.ID))
		return self.ID


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


	@classmethod
	def _find_record(cls, query: int):
		assert isinstance(query, int), f'Invalid query: {query!r}'
		out = cls._conn.execute(f'SELECT * FROM transactions WHERE id = ?', (query,)).fetchone()
		(ID, date, location, sender, amount, unit,
		 receiver, received_amount, received_unit, description, reference, report) = out
		assert query == ID, f'Expected ID {query}, got {ID}'
		# sender = Account.find(sender)
		# unit = Asset.find(unit)
		# receiver = Account.find(receiver)
		# received_unit = Asset.find(received_unit)
		# report = Report.find(report)
		return cls(ID, date, location, sender, amount, unit, receiver, received_amount, received_unit,
				   description, reference, report)


	def write(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = ('INSERT INTO transactions (dateof, location, sender, amount, unit, receiver, received_amount, '
			   'received_unit, description, reference, report) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
		conn.execute(cmd, (self.date, self.location, self.sender.ID, self.amount, self.unit.ID,
						   self.receiver.ID, self.received_amount,
						   self.received_unit.ID if self.received_unit else None,
						   self.description, self.reference,
						   report.ID))
		return conn.cursor().lastrowid


	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = ('UPDATE transactions SET dateof = ?, location = ?, sender = ?, amount = ?, unit = ?, receiver = ?, '
			   'received_amount = ?, received_unit = ?, description = ?, reference = ?, report = ? WHERE id = ?')
		conn.execute(cmd, (self.date, self.location, self.sender.ID, self.amount, self.unit.ID,
						   self.receiver.ID, self.received_amount,
						   self.received_unit.ID if self.received_unit else None,
						   self.description, self.reference,
						   report.ID, self.ID))
		return self.ID


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


	@classmethod
	def _find_record(cls, query: int):
		assert isinstance(query, int), f'Invalid query: {query!r}'
		out = cls._conn.execute(f'SELECT * FROM verifications WHERE id = ?', (query,)).fetchone()
		(ID, txn, date, location, sender, amount, unit,
		 receiver, received_amount, received_unit, description, reference, report) = out
		assert query == ID, f'Expected ID {query}, got {ID}'
		# txn = Transaction.find(txn)
		# sender = Account.find(sender)
		# unit = Asset.find(unit)
		# receiver = Account.find(receiver)
		# received_unit = Asset.find(received_unit)
		# report = Report.find(report)
		return cls(ID, txn, date, location, sender, amount, unit, receiver, received_amount, received_unit,
				   description, reference, report)


	def write(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')

		cmd = ('INSERT INTO verifications (txn, dateof, location, sender, amount, unit, receiver, received_amount, '
			   'received_unit, description, reference, report) VALUES (?,?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
		conn.execute(cmd, (self.txn.ID, self.date, self.location, self.sender.ID, self.amount, self.unit.ID,
						   self.receiver.ID, self.received_amount,
						   self.received_unit.ID if self.received_unit else None,
						   self.description, self.reference,
						   report.ID))

		return conn.cursor().lastrowid

	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = ('UPDATE verifications SET txn = ?, dateof = ?, location = ?, sender = ?, amount = ?, unit = ?, receiver = ?, '
			   'received_amount = ?, received_unit = ?, description = ?, reference = ?, report = ? WHERE id = ?')
		conn.execute(cmd, (self.txn.ID, self.date, self.location, self.sender.ID, self.amount, self.unit.ID,
						   self.receiver.ID, self.received_amount,
						   self.received_unit.ID if self.received_unit else None,
						   self.description, self.reference,
						   report.ID, self.ID))
		return self.ID






