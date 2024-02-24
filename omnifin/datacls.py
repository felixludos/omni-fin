import humanize

from .imports import *
from .errors import ConnectionNotSet, NoRecordFound



class sub:
	def __init__(self, record_type: Type['Record']):
		self.record_type = record_type
		self.value = None

	def __get__(self, instance, owner):
		value = self.value
		if isinstance(value, (int, str)):
			value = self.record_type.find(value)
			self.value = value
		return value

	def __set__(self, instance, value):
		self.value = value


@dataclass
class Record:
	ID: int = None


	@property
	def exists(self):
		return self.ID is not None


	_conn: sqlite3.Connection = None
	@classmethod
	def set_conn(cls, conn):
		cls._conn = conn


	# def __new__(cls, *args, **kwargs):
	# 	if cls._conn is not None:
	# 		return cls.find(*args, **kwargs)
	# 	return super().__new__(cls)

	# @classmethod
	# def _find_from_ID(cls, ID):
	# 	return cls._find_record(ID)

	# name of the sql table
	_table_name = None

	# mapping from attributes -> table columns (if they are different)
	_table_keys = None

	# primary key for the table
	_id_key = 'id'

	# optional column to use for queries
	_query_key = None

	# list of attributes to use for writing to the table
	_content_keys = None


	def write(self, *, cursor=None, force=False):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			items = {self._table_keys.get(key, key): getattr(self, key) for key in self._content_keys}
			items = {key: val.ID if isinstance(val, Record) else val for key, val in items.items()}
			cmd = f'INSERT INTO {self._table_name} ({", ".join(items.keys())}) VALUES ({", ".join("?"*len(items))})'
			cursor.execute(cmd, tuple(items.values()))
			self.ID = cursor.lastrowid
		return self.ID


	def update(self, *, cursor=None):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(cursor=cursor)

		items = {self._table_keys.get(key, key): getattr(self, key) for key in self._content_keys}
		items = {key: val.ID if isinstance(val, Record) else val for key, val in items.items()}
		key_info = ", ".join(f"{key} = ?" for key in items.keys())
		cmd = f'UPDATE {self._table_name} SET {key_info} WHERE {self._id_key} = ?'
		cursor.execute(cmd, tuple(items.values()))
		return self.ID


	def _volatile(self):
		return colorize('*', 'red') if self.exists else ''


	@classmethod
	def find(cls, query: str | int):
		if isinstance(query, str):
			try:
				query = int(query)
			except TypeError:
				pass
		assert isinstance(query, int) or cls._query_key is not None, f'Invalid query: {query!r}'
		if cls._conn is None:
			raise ConnectionNotSet()
		raw = None
		for key in [cls._id_key] if cls._query_key is None else [cls._query_key, cls._id_key]:
			for value in [query, query.lower(), query.upper()] if isinstance(query, str) else [query]:
				try:
					raw = cls._conn.execute(f'SELECT * FROM {cls._table_name} WHERE {key} = ?',
											(value,)).fetchone()
				except sqlite3.OperationalError:
					pass
		if raw is not None:
			return cls._from_row(*raw)
		raise NoRecordFound(query)


	@classmethod
	def _from_row(cls, ID, *data):
		return cls(*data, ID=ID)


	@classmethod
	def find_all(cls, **props):
		if len(props):
			query = ' AND '.join(f'{cls._table_keys.get(k, k)} = ?' for k in props)
			out = cls._conn.execute(f'SELECT * FROM {cls._table_name} WHERE {query}',
									tuple(props.values())).fetchall()
		else:
			out = cls._conn.execute(f'SELECT * FROM {cls._table_name}').fetchall()

		for row in out:
			yield cls._from_row(*row)



@dataclass
class Report(Record):
	def __init__(self, category: str = None, *, created: datelike = None, **kwargs):
		if created is None:
			created = datetime.now()
		super().__init__(**kwargs)
		self.category = category
		self.created = created


	category: str = None
	account: 'Account' = None
	description: str = None
	created: datelike = None


	_table_name = 'reports'
	_content_keys = 'category', 'account', 'description', 'created'
	_table_keys = {'id': 'ID', 'account': 'associated_account', 'created': 'created_at'}


	@classmethod
	def _from_row(cls, ID, category, account, description, created):
		return cls(ID=ID, category=category, account=account, description=description, created=created)


	def __str__(self):
		return (f'{self._volatile()}{colorize(self.category, "cyan")}'
				f'[{humanize.naturaldelta(datetime.now() - self.created)} ago]')


	def __repr__(self):
		return (f'{self.__class__.__name__}{self._volatile()}({colorize(self.category, "cyan")}, '
				f'{self.created.strftime("%y-%m-%d %H:%M:%S")})')



@dataclass
class Reportable(Record):
	report: Report = sub(Report)


	def write(self, report: Report, *, cursor=None, force=False):
		if self.exists:
			return self.update(report, cursor=cursor)
		self.report = report
		return super().write(cursor=cursor, force=force)


	def update(self, report: Report, *, cursor=None):
		if self.exists:
			self.report = report
			return super().update(cursor=cursor)
		return self.write(report, cursor=cursor)



@dataclass
class Asset(Reportable):
	def __init__(self, name: str = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name


	name: str = None
	category: str = None
	description: str = None


	@classmethod
	def _from_row(cls, ID, name, category, description, report):
		return cls(ID=ID, name=name, category=category, description=description, report=report)


	def __str__(self):
		return f'{self._volatile()}{colorize(self.name, "green")}'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "green")})'



class Tag(Reportable):
	def __init__(self, name: str = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name


	name: str = None
	category: str = None
	description: str = None


	@classmethod
	def _from_row(cls, ID, name, category, description, report):
		return cls(ID=ID, name=name, category=category, description=description, report=report)


	def __str__(self):
		return f'<{self._volatile()}{colorize(self.name, "yellow")}>'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "yellow")})'


@dataclass
class Account(Reportable):
	def __init__(self, name: str = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name


	name: str = None
	category: str = None
	owner: str = None
	description: str = None


	def __str__(self):
		return f'{self._volatile()}{colorize(self.name, "blue")}'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "blue")})'


	@classmethod
	def _from_row(cls, ID, name, category, owner, description, report):
		return cls(ID=ID, name=name, category=category, owner=owner, description=description, report=report)



Report.account = sub(Account)



@dataclass
class Statement(Reportable):
	def __init__(self, date: datelike = None, account: Account = None, balance: float = None, unit: Asset = None,
				 description: str = None, report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.date = date
		self.account = account
		self.balance = balance
		self.unit = unit
		self.description = description
		self.report = report

	date: datelike = None
	account: Account = sub(Account)
	balance: float = None
	unit: Asset = sub(Asset)
	description: str = None


	def __str__(self):
		return f'<{self._volatile()}{self.date.strftime("%y-%m-%d")} {self.account} :: {self.balance:.2f} {self.unit}>'


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 		f'{self.account}, {self.balance:.2f}, {self.unit})')
		return str(self)



@dataclass
class Transaction(Reportable):
	date: datelike = None
	location: str = None
	sender: Account = sub(Account)
	amount: float = None
	unit: Asset = sub(Asset)
	receiver: Account = sub(Account)
	received_amount: float = None
	received_unit: Asset = sub(Asset)
	description: str = None
	reference: str = None


	def __str__(self):
		return (f'<{self._volatile()}{self.date.strftime("%y-%m-%d")} {self.amount:.2f} {self.unit} '
				f'{self.sender} -> {self.receiver}>') if self.received_amount is None else (
			f'<{self._volatile()}{self.date.strftime("%y-%m-%d")} {self.amount:.2f} {self.unit} '
			f'{self.sender} -> {self.received_amount:.2f} {self.received_unit} {self.receiver}>')


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 		f'{self.amount:.2f}, {self.unit}, {self.sender}, {self.receiver})') if self.received_amount is None \
		# 	else (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 	f'{self.amount:.2f}, {self.unit}, {self.sender}, '
		# 	f'{self.received_amount:.2f}, {self.received_unit}, {self.receiver})')
		return str(self)



@dataclass
class Verification(Reportable):
	txn: Transaction = None
	date: datelike = None
	location: str = None
	sender: Account = sub(Account)
	amount: float = None
	unit: Asset = sub(Asset)
	receiver: Account = sub(Account)
	received_amount: float = None
	received_unit: Asset = sub(Asset)
	description: str = None
	reference: str = None



