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


class RecordBase:
	@property
	def exists(self):
		raise NotImplementedError


	_conn: sqlite3.Connection = None
	@classmethod
	def set_conn(cls, conn):
		RecordBase._conn = conn


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


	def _table_row_data(self, raw: dict = None):
		items = {self._table_keys.get(key, key): raw.get(key, getattr(self, key)) for key in self._content_keys}
		items = {key: val.ID if isinstance(val, Record) else val for key, val in items.items()}
		return items


	def write(self, *, cursor=None, force=False):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists or force:
			items = self._table_row_data()
			cmd = f'INSERT INTO {self._table_name} ({", ".join(items.keys())}) VALUES ({", ".join("?"*len(items))})'
			cursor.execute(cmd, tuple(items.values()))
			return cursor.lastrowid


	def update(self, *, cursor=None):
		if cursor is None:
			cursor = self._conn.cursor()
		if cursor is None:
			raise ValueError('No connection provided')
		if not self.exists:
			return self.write(cursor=cursor)
		items = self._table_row_data()
		key_info = ", ".join(f"{key} = ?" for key in items.keys())
		cmd = f'UPDATE {self._table_name} SET {key_info} WHERE {self._id_key} = ?'
		cursor.execute(cmd, tuple(items.values()))
		return cursor.lastrowid


	def _volatile(self):
		return '' if self.exists else colorize('*', 'red')


	@classmethod
	def find(cls, query: str | int):
		if isinstance(query, cls):
			return query
		assert not isinstance(query, Record), f'Invalid query: {query!r}'
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
class Record(RecordBase):
	ID: int = None

	@property
	def exists(self):
		return self.ID is not None


	def write(self, *, cursor=None, force=False):
		ID = super().write(cursor=cursor, force=force)
		if ID is not None and self.ID is None:
			self.ID = ID
		return ID


	def update(self, *, cursor=None):
		ID = super().update(cursor=cursor)
		assert self.ID == ID, f'invalid ID: {ID} != {self.ID}'
		return ID



@dataclass
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


	category: str = None
	account: 'Account' = None
	description: str = None
	created: datelike = None


	_table_name = 'reports'
	_content_keys = 'category', 'account', 'description', 'created'
	_table_keys = {'ID': 'id', 'account': 'associated_account', 'created': 'created_at'}


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
class Reportable(RecordBase):
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
	def __init__(self, name: str = None, *, category: str = None, description: str = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name
		self.category = category
		self.description = description


	name: str = None
	category: str = None
	description: str = None

	_table_name = 'assets'
	_query_key = 'name'
	_content_keys = 'name', 'category', 'description'
	_table_keys = {'ID': 'id', 'name': 'asset_name', 'category': 'asset_type'}


	@classmethod
	def _from_row(cls, ID, name, category, description, report):
		return cls(ID=ID, name=name, category=category, description=description, report=report)


	def __str__(self):
		return f'{self._volatile()}{colorize(self.name, "green")}'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "green")})'



class Tag(Reportable):
	def __init__(self, name: str = None, category: str = None, description: str = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name
		self.category = category
		self.description = description


	name: str = None
	category: str = None
	description: str = None

	_table_name = 'tags'
	_query_key = 'name'
	_content_keys = 'name', 'category', 'description'
	_table_keys = {'id': 'ID', 'name': 'tag_name'}


	@classmethod
	def _from_row(cls, ID, name, category, description, report):
		return cls(ID=ID, name=name, category=category, description=description, report=report)


	def __str__(self):
		return f'<{self._volatile()}{colorize(self.name, "yellow")}>'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "yellow")})'



class Linkable(Reportable):
	pass



@dataclass
class Link(Reportable):
	category: str = None
	# id1: int = None
	# id2: int = None

	# _table_name = ''
	_node_keys = None
	_content_keys = None
	_table_keys = {'category': 'link_type'}


	def _table_row_data(self, raw: dict = None):
		keys = *self._node_keys, self._content_keys
		items = {self._table_keys.get(key, key): raw.get(key, getattr(self, key)) for key in keys}
		items = {key: val.ID if isinstance(val, Record) else val for key, val in items.items()}
		return items



class UndirectedLink(Link):
	def _table_row_data(self, raw: dict = None):
		data = super()._table_row_data(raw)
		data['id1'], data['id2'] = sorted((data['id1'], data['id2']))
		return data



class Tagged(Record):
	_tag_table_name = None


	def add_tags(self, report: Report, *tags: str | Tag, cursor=None):
		assert report.exists, 'Report not written to database'
		assert self.ID is not None, 'Transaction not written to database'
		if cursor is None:
			cursor = self._conn.cursor()
		existing = set(self.tags())
		for tag in tags:
			tag = Tag.find(tag)
			if tag not in existing:
				assert tag.exists, f'No tag found for {tag}'
				cursor.execute(f'INSERT INTO {self._tag_table_name} (id, tag_id) VALUES (?, ?)', (self.ID, tag.ID))


	def tags(self):
		assert self.ID is not None, 'Transaction not written to database'
		query = f'SELECT tag_id FROM {self._tag_table_name} WHERE {self._id_key} = ?'
		cursor = self._conn.execute(query, (self.ID,))
		for tag, in cursor.fetchall():
			yield Tag.find(tag)



@dataclass
class Account(Reportable, Tagged):
	def __init__(self, name: str = None, *, category: str = None, owner: str = None, description: str = None, **kwargs):
		super().__init__(**kwargs)
		self.name = name
		self.category = category
		self.owner = owner
		self.description = description


	name: str = None
	category: str = None
	owner: str = None
	description: str = None


	_table_name = 'accounts'
	_tag_table_name = 'account_tags'
	_query_key = 'name'
	_content_keys = 'name', 'category', 'owner', 'description'
	_table_keys = {'ID': 'id', 'name': 'account_name', 'category': 'account_type', 'owner': 'account_owner'}


	def __str__(self):
		return f'{self._volatile()}{colorize(self.name, "blue")}'


	def __repr__(self):
		return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "blue")})'


	@classmethod
	def _from_row(cls, ID, name, category, owner, description, report):
		return cls(ID=ID, name=name, category=category, owner=owner, description=description, report=report)

Report.account = sub(Account)



@dataclass
class Statement(Reportable, Tagged):
	date: datelike = None
	account: Account = sub(Account)
	balance: float = None
	unit: Asset = sub(Asset)
	description: str = None


	_table_name = 'statements'
	_tag_table_name = 'statement_tags'
	_content_keys = 'date', 'account', 'balance', 'unit', 'description'
	_table_keys = {'ID': 'id', 'date': 'dateof'}


	@classmethod
	def _from_row(cls, ID, *data):
		return cls(ID=ID, date=data[0], account=data[1], balance=data[2], unit=data[3], description=data[4],
				   report=data[5])


	def __str__(self):
		return f'<{self._volatile()}{self.date.strftime("%y-%m-%d")} {self.account} :: {self.balance:.2f} {self.unit}>'


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 		f'{self.account}, {self.balance:.2f}, {self.unit})')
		return str(self)



@dataclass
class Transaction(Reportable, Tagged):
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


	_table_name = 'transactions'
	_tag_table_name = 'transaction_tags'
	_content_keys = ('date', 'location', 'sender', 'amount', 'unit',
					 'receiver', 'received_amount', 'received_unit',
					 'description', 'reference')
	_table_keys = {'ID': 'id', 'date': 'dateof'}


	@classmethod
	def _from_row(cls, ID, *data):
		return cls(ID=ID, date=data[0], location=data[1], sender=data[2], amount=data[3], unit=data[4],
					receiver=data[5], received_amount=data[6], received_unit=data[7], description=data[8],
					reference=data[9], report=data[10])


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
class TransactionLink(Link):
	txn1: Transaction = sub(Transaction)
	txn2: Transaction = sub(Transaction)

	_table_name = 'transaction_links'
	_node_keys = 'txn1', 'txn2'
	_content_keys = 'category'
	_table_keys = {'category': 'link_type', 'txn1': 'id1', 'txn2': 'id2'}



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


	_table_name = 'verifications'
	_content_keys = ('txn', 'date', 'location', 'sender', 'amount', 'unit',
					 'receiver', 'received_amount', 'received_unit',
					 'description', 'reference')
	_table_keys = {'ID': 'id', 'date': 'dateof'}


	@classmethod
	def _from_row(cls, ID, txn, date, location, sender, amount, unit, receiver, received_amount, received_unit,
				  description, reference, report):
		return cls(ID=ID, txn=txn, date=date, location=location, sender=sender, amount=amount, unit=unit,
				   receiver=receiver, received_amount=received_amount, received_unit=received_unit,
				   description=description, reference=reference, report=report)


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


