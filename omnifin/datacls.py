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
			except ValueError:
				pass
		assert isinstance(query, int) or cls._query_key is not None, f'Invalid query: {query!r}'
		if cls._conn is None:
			raise ConnectionNotSet()
		for key in [cls._id_key] if cls._query_key is None else [cls._query_key, cls._id_key]:
			for value in [query, query.lower(), query.upper()] if isinstance(query, str) else [query]:
				command = f'SELECT * FROM {cls._table_name} WHERE {cls._table_keys.get(key, key)} = ?'
				raw = cls._conn.execute(command, (value,)).fetchone()
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
	def __init__(self, *, ID: int = None, **kwargs):
		super().__init__(**kwargs)
		self.ID = ID


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
		accinfo = '' if self.account is None else f' (account={self.account})'
		return (f'{self._volatile()}{colorize(self.category, "cyan")} '
				f'{humanize.naturaldelta(datetime.now() - self.created)} ago{accinfo}')


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({colorize(self.category, "cyan")}, '
		# 		f'{self.created.strftime("%y-%m-%d %H:%M:%S")})')
		return str(self)


@dataclass
class Reportable(RecordBase):
	def __init__(self, *, report: Report = None, **kwargs):
		super().__init__(**kwargs)
		self.report = report


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
class Asset(Record, Reportable):
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
		# return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "green")})'
		return str(self)



class Tag(Record, Reportable):
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
		# return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "yellow")})'
		return str(self)



@dataclass
class Link(Record, Reportable):
	category: str = None

	# _table_name = ''
	_node_keys = None
	_content_keys = None
	_table_keys = {'category': 'link_type'}


	def _table_row_data(self, raw: dict = None):
		keys = *self._node_keys, self._content_keys
		items = {self._table_keys.get(key, key): raw.get(key, getattr(self, key)) for key in keys}
		items = {key: val.ID if isinstance(val, Record) else val for key, val in items.items()}
		return items


	def all_links(self, category: str = None):
		if category is None:
			query = f'SELECT * FROM {self._table_name}'
			cursor = self._conn.execute(query)
		else:
			query = f'SELECT * FROM {self._table_name} WHERE {self._table_keys["category"]} = ?'
			cursor = self._conn.execute(query, (category,))
		for row in cursor.fetchall():
			yield self._from_row(*row)



class Linkable(Reportable):
	_link_type: Type[Link] = None

	def get_links(self, category: str = None):
		raise NotImplementedError

	def add_links(self, report: Report, *links: Link, category: str = None, cursor=None):
		raise NotImplementedError



class Directed(Link):
	@classmethod
	def children_of(cls, record: Linkable, category: str = None):
		query = (f'SELECT * FROM {cls._table_name} WHERE id1 = ?' if category is None
				 else f'SELECT * FROM {cls._table_name} WHERE id1 = ? AND {cls._table_keys["category"]} = ?')
		cursor = cls._conn.execute(query, (record.ID,) if category is None else (record.ID, category))
		for row in cursor.fetchall():
			yield cls._from_row(*row)


	@classmethod
	def parents_of(cls, record: Linkable, category: str = None):
		query = (f'SELECT * FROM {cls._table_name} WHERE id2 = ?' if category is None
				 else f'SELECT * FROM {cls._table_name} WHERE id2 = ? AND {cls._table_keys["category"]} = ?')
		cursor = cls._conn.execute(query, (record.ID,) if category is None else (record.ID, category))
		for row in cursor.fetchall():
			yield cls._from_row(*row)



class Undirected(Link):
	def _table_row_data(self, raw: dict = None):
		data = super()._table_row_data(raw)
		data['id1'], data['id2'] = sorted((data['id1'], data['id2']))
		return data


	@classmethod
	def of(cls, record: Linkable, category: str = None):
		query = (f'SELECT * FROM {cls._table_name} WHERE (id1 = ? OR id2 = ?)' if category is None
				 else f'SELECT * FROM {cls._table_name} WHERE (id1 = ? OR id2 = ?) '
					  f'AND {cls._table_keys["category"]} = ?')
		cursor = cls._conn.execute(query, (record.ID, record.ID) if category is None
											else (record.ID, record.ID, category))
		for row in cursor.fetchall():
			yield cls._from_row(*row)


	@classmethod
	def cluster(cls, record: Linkable, category: str = None):
		_completed = set()
		yield from cls._cluster(_completed, record, category=category)


	@classmethod
	def _cluster(cls, _completed: set, record: Linkable, category: str = None):
		_completed.add(record.ID)
		for link in cls.of(record, category):
			rec1, rec2 = getattr(link, cls._node_keys[0]), getattr(link, cls._node_keys[1])
			other = rec2 if rec1.ID == record.ID else rec1
			if other not in _completed:
				yield from cls.cluster(_completed, other, category)
		yield record



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
class Account(Tagged, Linkable, Record, Reportable):
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
		# return f'{self.__class__.__name__}{self._volatile()}({colorize(self.name, "blue")})'
		return str(self)


	@classmethod
	def _from_row(cls, ID, name, category, owner, description, report):
		return cls(ID=ID, name=name, category=category, owner=owner, description=description, report=report)

Report.account = sub(Account)



@dataclass
class Statement(Linkable, Tagged):
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
	def _from_row(cls, ID, date, account, balance, unit, description, report):
		return cls(ID=ID, date=date, account=account, balance=balance, unit=unit, description=description,
				   report=report)


	def __str__(self):
		return (f'[{self._volatile() or " "}{self.date.strftime("%d-%b%y")} {self.account} '
				f':: {self.balance:.2f} {self.unit} ]')


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 		f'{self.account}, {self.balance:.2f}, {self.unit})')
		return str(self)


	def get_links(self, category: str = None):
		for link in self._link_type.cluster(self, category=category):
			yield link.state2 if link.state1 == self else link.state1


	def add_links(self, report: Report, *statements: 'Statement', category: str = None, cursor=None):
		assert report.exists, 'Report not written to database'
		assert self.exists, 'Transaction not written to database'
		if cursor is None:
			cursor = self._conn.cursor()
		existing = set(self.get_links(category))
		new = []
		for other in statements:
			if other not in existing:
				self._link_type(category=category, state1=self, state2=other, report=report).write(cursor=cursor)
				new.append(other)
		return new


@dataclass
class StatementLink(Undirected):
	state1: Statement = sub(Statement)
	state2: Statement = sub(Statement)

	_table_name = 'statement_links'
	_node_keys = 'state1', 'state2'
	_content_keys = 'category'
	_table_keys = {'category': 'link_type', 'state1': 'id1', 'state2': 'id2'}

	@classmethod
	def _from_row(cls, state1, state2, category, report):
		return cls(state1=state1, state2=state2, category=category, report=report)

Statement._link_type = StatementLink


@dataclass
class Transaction(Linkable, Tagged):
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
	def _from_row(cls, ID, date, location, sender, amount, unit, receiver, received_amount, received_unit,
				  description, reference, report):
		return cls(ID=ID, date=date, location=location, sender=sender, amount=amount, unit=unit,
				   receiver=receiver, received_amount=received_amount, received_unit=received_unit,
				   description=description, reference=reference, report=report)


	def __str__(self):
		return (f'[{self._volatile() or " "}{self.date.strftime("%d-%b%y")} {self.amount:.2f} {self.unit} '
				f'{self.sender} -> {self.receiver} ]') if self.received_amount is None else (
			f'[{self._volatile() or " "}{self.date.strftime("%d-%b%y")} {self.amount:.2f} {self.unit} '
			f'{self.sender} -> {self.received_amount:.2f} {self.received_unit} {self.receiver} ]')


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 		f'{self.amount:.2f}, {self.unit}, {self.sender}, {self.receiver})') if self.received_amount is None \
		# 	else (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 	f'{self.amount:.2f}, {self.unit}, {self.sender}, '
		# 	f'{self.received_amount:.2f}, {self.received_unit}, {self.receiver})')
		return str(self)


	def get_links(self, category: str = None):
		for link in self._link_type.cluster(self, category=category):
			yield link.txn2 if link.txn1 == self else link.txn1


	def add_links(self, report: Report, *links: Link, category: str = None, cursor=None):
		assert report.exists, 'Report not written to database'
		assert self.exists, 'Transaction not written to database'
		if cursor is None:
			cursor = self._conn.cursor()
		existing = set(self.get_links(category))
		new = []
		for other in links:
			if other not in existing:
				self._link_type(txn1=self, txn2=other, category=category, report=report).write(cursor=cursor)
				new.append(other)
		return new


@dataclass
class TransactionLink(Undirected):
	txn1: Transaction = sub(Transaction)
	txn2: Transaction = sub(Transaction)

	_table_name = 'transaction_links'
	_node_keys = 'txn1', 'txn2'
	_content_keys = 'category'
	_table_keys = {'category': 'link_type', 'txn1': 'id1', 'txn2': 'id2'}

	@classmethod
	def _from_row(cls, txn1, txn2, category, report):
		return cls(txn1=txn1, txn2=txn2, category=category, report=report)

Transaction._link_type = TransactionLink


@dataclass
class Verification(Reportable, Record):
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
		return (f'[{self._volatile() or " "}{self.date.strftime("%d-%b%y")} {self.amount:.2f} {self.unit} '
				f'{self.sender} -> {self.receiver} ]') if self.received_amount is None else (
			f'[{self._volatile() or " "}{self.date.strftime("%d-%b%y")} {self.amount:.2f} {self.unit} '
			f'{self.sender} -> {self.received_amount:.2f} {self.received_unit} {self.receiver} ]')


	def __repr__(self):
		# return (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 		f'{self.amount:.2f}, {self.unit}, {self.sender}, {self.receiver})') if self.received_amount is None \
		# 	else (f'{self.__class__.__name__}{self._volatile()}({self.date.strftime("%y-%m-%d")}, '
		# 	f'{self.amount:.2f}, {self.unit}, {self.sender}, '
		# 	f'{self.received_amount:.2f}, {self.received_unit}, {self.receiver})')
		return str(self)


