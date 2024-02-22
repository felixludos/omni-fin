import humanize

from .imports import *



class RecordBase():
	def __init__(self, *, ID: int = None):
		self.ID = ID


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


	def _volatile(self):
		return colorize('*' if self.ID is None else '', 'red')


	@classmethod
	def clear_cache(cls):
		cls._cache.clear()


	_cache = None
	@classmethod
	def _find_record(self, query: str | int, **props):
		raise NotImplementedError
	@classmethod
	def find(cls, query: str | int, **props):
		if query is None and len(props) == 0:
			return None
		return cls._cache.setdefault(query, cls._find_record(query, **props))

	@classmethod
	def find_all(cls, **props):
		raise NotImplementedError



class Report(Record):
	def __init__(self, category: str = None, *, account: 'Account' = None, description: str = None,
				 created: datelike = None, **kwargs):
		if created is None:
			created = datetime.now()
		super().__init__(**kwargs)
		self.category = category
		self.account = account
		self.description = description
		self.created = created


	@property
	def account(self):
		value = self._account
		if isinstance(value, (int, str)):
			value = Account.find(value)
			self._account = value
		return value
	@account.setter
	def account(self, value):
		self._account = value


	def __str__(self):
		return f'{self._volatile()}{colorize(self.category, "cyan")}[{humanize.naturaldelta(datetime.now() - self.created)} ago]'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.category, "cyan")}, {self.created.strftime("%y-%m-%d %H:%M:%S")})'


	@classmethod
	def _find_record(cls, query: int):
		assert isinstance(query, int), f'Invalid query: {query!r}'
		out = cls._conn.execute(f'SELECT * FROM reports WHERE id = ?', (query,)).fetchone()
		ID, category, account, description, created = out
		assert query == ID, f'Expected ID {query}, got {ID}'
		# account = Account.find(account)
		return cls(ID=ID, category=category, account=account, description=description, created=created)


	def write(self, *, cursor=None, force=False):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = 'INSERT INTO reports (category, associated_account, description) VALUES (?, ?, ?)'
			cursor.execute(cmd, (self.category, self.account.ID if self.account else None, self.description))
			self.ID = cursor.lastrowid
		return self.ID



class Asset(Record):
	def __init__(self, name: str = None, *, category: str = None, description: str = None,
				 report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name
		self.category = category
		self.description = description
		self.report = report


	@property
	def report(self):
		value = self._report
		if isinstance(value, (int, str)):
			value = Report.find(value)
			self._report = value
		return value
	@report.setter
	def report(self, value):
		self._report = value


	def __str__(self):
		return f'{self._volatile()}{colorize(self.name, "green")}'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "green")})'


	@classmethod
	def _find_record(cls, query: str | int):
		out = cls._conn.execute(f'SELECT * FROM assets WHERE {"id" if isinstance(query, int) else "asset_name"} = ?',
								(query,)).fetchone()
		ID, name, category, description, report = out
		# report = Report.find(report)
		return cls(ID=ID, name=name, category=category, description=description, report=report)


	def write(self, report: Report, *, cursor=None, force=False):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = 'INSERT INTO assets (asset_name, asset_type, description, report) VALUES (?, ?, ?, ?)'
			cursor.execute(cmd, (self.name, self.category, self.description, report.ID))
			self.ID = cursor.lastrowid
		else:
			self.update(report, cursor)
		return self.ID


	def update(self, report: Report, *, cursor=None):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, cursor)

		cmd = 'UPDATE assets SET asset_name = ?, asset_type = ?, description = ?, report = ? WHERE id = ?'
		cursor.execute(cmd, (self.name, self.category, self.description, report.ID, self.ID))
		return self.ID


class Tag(Record):
	def __init__(self, name: str = None, *, category: str = None, description: str = None,
				 report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name
		self.category = category
		self.description = description
		self.report = report


	@classmethod
	def _find_record(cls, query: str | int):
		out = cls._conn.execute(f'SELECT * FROM tags WHERE {"id" if isinstance(query, int) else "tag_name"} = ?',
								(query,)).fetchone()
		ID, name, category, description, report = out
		# report = Report.find(report)
		return cls(ID=ID, name=name, category=category, description=description, report=report)


	def write(self, report: Report, *, conn=None, force=False):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = 'INSERT INTO tags (tag_name, category, description, report) VALUES (?, ?, ?, ?)'
			conn.execute(cmd, (self.name, self.category, self.description, report.ID))
			self.ID = conn.cursor().lastrowid
		else:
			self.update(report, conn)
		return self.ID


	def update(self, report: Report, *, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = 'UPDATE tags SET tag_name = ?, category = ?, description = ?, report = ? WHERE id = ?'
		conn.execute(cmd, (self.name, self.category, self.description, report.ID, self.ID))
		return self.ID


class Account(Record):
	def __init__(self, name: str = None, *, category: str = None, owner: str = None, description: str = None,
				 report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name
		self.category = category
		self.owner = owner
		self.description = description
		self.report = report


	def __str__(self):
		return f'{self._volatile()}{colorize(self.name, "yellow")}'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "yellow")})'


	@classmethod
	def _find_record(cls, query: str | int):
		out = cls._conn.execute(f'SELECT * FROM accounts WHERE {"id" if isinstance(query, int) else "account_name"} = ?',
								(query,)).fetchone()
		ID, name, category, owner, description, report = out
		# report = Report.find(report)
		return cls(ID=ID, name=name, category=category, owner=owner, description=description, report=report)


	def write(self, report: Report, *, conn=None, force=False):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = ('INSERT INTO accounts (account_name, account_type, account_owner, description, report) '
				   'VALUES (?, ?, ?, ?, ?)')
			conn.execute(cmd, (self.name, self.category, self.owner, self.description, report.ID))
			self.ID = conn.cursor().lastrowid
		else:
			self.update(report, conn)
		return self.ID


	def update(self, report: Report, *, conn=None):
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



class Statement(Record):
	def __init__(self, date: datelike = None, account: Account = None, balance: float = None, unit: Asset = None,
				 description: str = None, report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.date = date
		self.account = account
		self.balance = balance
		self.unit = unit
		self.description = description
		self.report = report


	@property
	def account(self):
		value = self._account
		if isinstance(value, (int, str)):
			value = Account.find(value)
			self._account = value
		return value
	@account.setter
	def account(self, value):
		self._account = value


	@property
	def unit(self):
		value = self._unit
		if isinstance(value, (int, str)):
			value = Asset.find(value)
			self._unit = value
		return value
	@unit.setter
	def unit(self, value):
		self._unit = value


	@property
	def report(self):
		value = self._report
		if isinstance(value, (int, str)):
			value = Report.find(value)
			self._report = value
		return value
	@report.setter
	def report(self, value):
		self._report = value


	# def __str__(self):
	# 	return f'{self._volatile()}{colorize(self.date.strftime("%y-%m-%d"), "blue")}'


	@classmethod
	def _find_record(cls, query: int):
		assert isinstance(query, int), f'Invalid query: {query!r}'
		out = cls._conn.execute(f'SELECT * FROM statements WHERE id = ?', (query,)).fetchone()
		ID, date, account, balance, unit, description, report = out
		assert query == ID, f'Expected ID {query}, got {ID}'
		# account = Account.find(account)
		# unit = Asset.find(unit)
		# report = Report.find(report)
		return cls(ID=ID, date=date, account=account, balance=balance, unit=unit, description=description,
				   report=report)

	def write(self, report: Report, conn=None, force=False):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = ('INSERT INTO statements (dateof, account, balance, unit, description, report) '
				   'VALUES (?, ?, ?, ?, ?, ?)')
			conn.execute(cmd, (self.date, self.account.ID, self.balance, self.unit.ID, self.description,
							   report.ID))
			self.ID = conn.cursor().lastrowid
		else:
			self.update(report, conn)
		return self.ID


	def update(self, report: Report, conn=None):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(report, conn)

		cmd = ('UPDATE statements SET dateof = ?, account = ?, balance = ?, unit = ?, description = ?, report = ? '
			   'WHERE id = ?')
		conn.execute(cmd, (self.date, self.account.ID, self.balance, self.unit.ID, self.description,
						   report.ID, self.ID))
		return self.ID



class Transaction(Record):
	def __init__(self, date: datelike = None, location: str = None, sender: Account = None, amount: float = None,
				 unit: Asset = None, receiver: Account = None, received_amount: float = None, received_unit: Asset = None,
				 description: str = None, reference: str = None, report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.date = date
		self.location = location
		self.sender = sender
		self.amount = amount
		self.unit = unit
		self.receiver = receiver
		self.received_amount = received_amount
		self.received_unit = received_unit
		self.description = description
		self.reference = reference
		self.report = report


	@property
	def sender(self):
		value = self._sender
		if isinstance(value, (int, str)):
			value = Account.find(value)
			self._sender = value
		return value
	@sender.setter
	def sender(self, value):
		self._sender = value


	@property
	def unit(self):
		value = self._unit
		if isinstance(value, (int, str)):
			value = Asset.find(value)
			self._unit = value
		return value
	@unit.setter
	def unit(self, value):
		self._unit = value


	@property
	def receiver(self):
		value = self._receiver
		if isinstance(value, (int, str)):
			value = Account.find(value)
			self._receiver = value
		return value
	@receiver.setter
	def receiver(self, value):
		self._receiver = value


	@property
	def received_unit(self):
		value = self._received_unit
		if isinstance(value, (int, str)):
			value = Asset.find(value)
			self._received_unit = value
		return value
	@received_unit.setter
	def received_unit(self, value):
		self._received_unit = value


	@property
	def report(self):
		value = self._report
		if isinstance(value, (int, str)):
			value = Report.find(value)
			self._report = value
		return value
	@report.setter
	def report(self, value):
		self._report = value


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
		return cls(ID=ID, date=date, location=location, sender=sender, amount=amount, unit=unit, receiver=receiver,
				   received_amount=received_amount, received_unit=received_unit, description=description,
				   reference=reference, report=report)


	def write(self, report: Report, conn=None, force=False):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = ('INSERT INTO transactions (dateof, location, sender, amount, unit, receiver, received_amount, '
				   'received_unit, description, reference, report) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
			conn.execute(cmd, (self.date, self.location, self.sender.ID, self.amount, self.unit.ID,
							   self.receiver.ID, self.received_amount,
							   self.received_unit.ID if self.received_unit else None,
							   self.description, self.reference,
							   report.ID))
			self.ID = conn.cursor().lastrowid
		else:
			self.update(report, conn)
		return self.ID


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



class Verification(Record):
	txn: Transaction = None
	date: datelike = None
	location: str = None
	sender: Account = None
	amount: float = None
	unit: Asset = None
	receiver: Account = None
	received_amount: float = None
	received_unit: Asset = None
	description: str = None
	reference: str = None
	report: Report = None

	def __init__(self, txn: Transaction = None, date: datelike = None, location: str = None, sender: Account = None,
				 amount: float = None, unit: Asset = None, receiver: Account = None, received_amount: float = None,
				 received_unit: Asset = None, description: str = None, reference: str = None, report: Report = None,
				 **kwargs):
		super().__init__(**kwargs)
		self.txn = txn
		self.date = date
		self.location = location
		self.sender = sender
		self.amount = amount
		self.unit = unit
		self.receiver = receiver
		self.received_amount = received_amount
		self.received_unit = received_unit
		self.description = description
		self.reference = reference
		self.report = report


	@property
	def txn(self):
		value = self._txn
		if isinstance(value, (int, str)):
			value = Transaction.find(value)
			self._txn = value
		return value
	@txn.setter
	def txn(self, value):
		self._txn = value


	@property
	def sender(self):
		value = self._sender
		if isinstance(value, (int, str)):
			value = Account.find(value)
			self._sender = value
		return value
	@sender.setter
	def sender(self, value):
		self._sender = value


	@property
	def unit(self):
		value = self._unit
		if isinstance(value, (int, str)):
			value = Asset.find(value)
			self._unit = value
		return value
	@unit.setter
	def unit(self, value):
		self._unit = value


	@property
	def receiver(self):
		value = self._receiver
		if isinstance(value, (int, str)):
			value = Account.find(value)
			self._receiver = value
		return value
	@receiver.setter
	def receiver(self, value):
		self._receiver = value


	@property
	def received_unit(self):
		value = self._received_unit
		if isinstance(value, (int, str)):
			value = Asset.find(value)
			self._received_unit = value
		return value
	@received_unit.setter
	def received_unit(self, value):
		self._received_unit = value


	@property
	def report(self):
		value = self._report
		if isinstance(value, (int, str)):
			value = Report.find(value)
			self._report = value
		return value
	@report.setter
	def report(self, value):
		self._report = value


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
		return cls(ID=ID, txn=txn, date=date, location=location, sender=sender, amount=amount, unit=unit,
				   receiver=receiver, received_amount=received_amount, received_unit=received_unit,
				   description=description, reference=reference, report=report)


	def write(self, report: Report, conn=None, force=False):
		if conn is None:
			conn = self._conn
		if conn is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			cmd = ('INSERT INTO verifications (txn, dateof, location, sender, amount, unit, receiver, received_amount, '
				   'received_unit, description, reference, report) VALUES (?,?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
			conn.execute(cmd, (self.txn.ID, self.date, self.location, self.sender.ID, self.amount, self.unit.ID,
							   self.receiver.ID, self.received_amount,
							   self.received_unit.ID if self.received_unit else None,
							   self.description, self.reference,
							   report.ID))
			self.ID = conn.cursor().lastrowid
		else:
			self.update(report, conn)
		return self.ID

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






