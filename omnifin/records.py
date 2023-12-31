from typing import Optional, Union, Type, TypeVar, Any, Callable, Iterable, Mapping, Sequence, Tuple, List, Dict
import sqlite3
from datetime import datetime, date as datelike
from dateutil import parser
import omnifig as fig



_known_record_types = {}



class Figged(fig.Configurable):
	@classmethod
	def init_from_config(cls, config: fig.Configuration,
						 args: Optional[Tuple] = None, kwargs: Optional[Dict[str, Any]] = None, *,
						 silent: Optional[bool] = None) -> Any:
		if kwargs is None:
			kwargs = {}

		if 'primary_key' not in kwargs:
			kwargs['primary_key'] = config.pull('primary_key', None, silent=silent)

		for key in cls.__annotations__:
			if key in kwargs:
				continue
			if key in config:
				kwargs[key] = config.pull(key, getattr(cls, key), silent=silent) if hasattr(cls, key) \
					else config.pull(key, silent=silent)

		return super().init_from_config(config, args=args, kwargs=kwargs, silent=silent)



class Record:
	_table_name = None
	_load_fn = None
	_record_cache = None
	def __init_subclass__(cls, table=None, **kwargs):
		super().__init_subclass__(**kwargs)
		_known_record_types[cls.__name__] = cls
		cls._table_name = table
		cls._record_cache = {}

	def set_ID(self, ID: int):
		# assert not self.exists(), f'Record {self} already exists'
		# if ID in self._record_cache:
		# 	raise ValueError(f"Record {self} already exists in cache.")
		# self.ID = ID
		# self._record_cache[ID] = self
		# self._loaded = True
		assert ID not in self._record_cache, f"Record {self} already exists in cache."
		self._primary_key = ID
		self.load()
		self._record_cache[ID] = self
		# return self.from_key(ID).load()
		return self

	def __new__(cls, primary_key=None, **kwargs):
		if primary_key is None:
			return super().__new__(cls)
		elif primary_key in cls._record_cache:
			return cls._record_cache[primary_key]
		else:
			new = super().__new__(cls)
			cls._record_cache[primary_key] = new
			return new

	def __init__(self, *, primary_key=None, **kwargs):
		info = {}
		for key, typ in self.__annotations__.items():
			if key in kwargs:
				info[key] = kwargs.pop(key)
		super().__init__(**kwargs)
		self._loaded = False
		self._primary_key = primary_key
		if len(info):
			self.update(info)

	def update(self, info):
		if self.exists():
			raise NotImplementedError(f"Cannot update loaded record: {self.primary_key}")
		if 'ID' in info:
			raise NotImplementedError(f'Cannot set ID of {self.__class__.__name__}.')
		self._populate_info(info)

	def exists(self):
		return self.primary_key is not None

	def as_dict(self) -> dict[str, Any]:
		return {key: getattr(self, key) for key, typ in self.__annotations__.items() if hasattr(self, key)}

	def _populate_info(self, info: dict[str, Any], strict=False):
		for key, val in info.items():
			typ = self.__annotations__.get(key, None)
			if typ is None:
				raise ValueError(f"Unknown key {key} for {self.__class__.__name__}")
			old = self.__dict__.get(key, None)
			if strict and old is not None and key in info:
				assert old == info[key], f"Value mismatch for {key}: {val} != {old}"
			self.__dict__[key] = val
			# setattr(self, key, info[key] if key in info else val)
			if isinstance(typ, str):
				typ = _known_record_types[typ]
			if issubclass(typ, datelike):
				if isinstance(val, str):
					val = parser.parse(val)  # .date()
					# setattr(self, key, val)
					self.__dict__[key] = val
			if issubclass(typ, Record):
				if isinstance(val, int):
					val = typ.from_key(val)
					# setattr(self, key, val)
					self.__dict__[key] = val

	def __getattr__(self, item):
		if item in self.__getattribute__('__annotations__') and self.__getattribute__('exists')():
			self.load()
		return self.__getattribute__(item)

	def __setattr__(self, key, value):
		if key in self.__annotations__ and self.exists():
			raise AttributeError(f"Cannot set {key!r} of a database record {self.primary_key}")
		super().__setattr__(key, value)

	@classmethod
	def _from_raw(cls, raw: Tuple):
		return {k: v for k, v in zip(cls.__annotations__, raw)}

	def __hash__(self):
		if not self.exists():
			return hash(self.as_dict())
		return hash(self.primary_key)

	def __eq__(self, other):
		if self.exists() and other.exists():
			return self.primary_key == other.primary_key
		return self.as_dict() == other.as_dict()

	def export_row(self, report):
		return [getattr(self, key) if key != 'report' else report for key in self.__annotations__ if key != 'ID']

	@property
	def table_name(self):
		return self._table_name

	@property
	def primary_key(self):
		return self.ID if self.is_loaded() else self._primary_key

	def is_loaded(self):
		return self._loaded

	@classmethod
	def from_key(cls, key: int):
		return cls(primary_key=key)

	def shortcuts(self) -> Iterable[str]:
		yield from ()

	def load(self, raw = None, *, strict=False):
		if self._loaded:
			if raw is not None and strict:
				raise NotImplementedError("Strict loading not implemented.")
		else:
			if self._load_fn is None:
				raise NotImplementedError("Loader function not set.")
			if self.table_name is None:
				raise NotImplementedError(f"Table name for {self.__class__.__name__} not set.")
			if raw is None:
				raw = self._load_fn(self.table_name, self._primary_key)
			self._populate_info(self._from_raw(raw))
			self._loaded = True
		return self

	def __loaded_str__(self):
		return super().__str__()

	def __loaded_repr__(self):
		return super().__repr__()

	def __str__(self):
		if not self.exists():
			return (f'{self.__class__.__name__}('
					f'{", ".join(f"{key}={val}" for key, val in self.as_dict().items() if val is not None)})')
		return self.__loaded_str__() if self.is_loaded() else f'{self.__class__.__name__}({self.primary_key})'

	def __repr__(self):
		if not self.exists():
			return (f'{self.__class__.__name__}('
					f'{", ".join(f"{key}={val}" for key, val in self.as_dict().items() if val is not None)})')
		return self.__loaded_repr__() if self.is_loaded() else f'{self.__class__.__name__}({self.primary_key})'



class Fillable(Record):
	_fill_fn = None

	@classmethod
	def from_raw(cls, raw: tuple):
		key = raw[0]
		obj = cls.from_key(key)
		obj.load(raw)
		return obj

	def fill(self):
		if self._fill_fn is None:
			raise NotImplementedError("Filler function not set.")
		if self.table_name is None:
			raise NotImplementedError(f"Table name {self.__class__.__name__} not set.")
		for raw in self._fill_fn(self.table_name, self.as_dict()):
			yield self.from_raw(raw)

	def in_db(self):
		if self.exists():
			return True
		try:
			next(self.fill())
		except StopIteration:
			return False
		return True



class Tagged(Fillable):
	_load_tags = None

	@property
	def tags_table_name(self):
		raise NotImplementedError

	def tags(self):
		existing = getattr(self, '_existing_tags', None)
		if existing is None and self.exists():
			if self.tags_table_name is None:
				raise NotImplementedError(f"Table name {self.__class__.__name__} not set.")
			existing = self._load_tags(self.tags_table_name, self.primary_key)
			setattr(self, '_existing_tags', existing)
		if existing is not None:
			yield from existing
		new = getattr(self, '_new_tags', None)
		if new is not None:
			yield from new

	def new_tags(self):
		yield from getattr(self, '_new_tags', ())

	def add_tag(self, *tags: 'Tag'):
		new = getattr(self, '_new_tags', None)
		if new is None:
			setattr(self, '_new_tags', [])
		new = getattr(self, '_new_tags')
		existing = getattr(self, '_existing_tags', None)
		new.extend(tag for tag in tags if tag not in new and (existing is None or tag not in existing))



class Linked(Fillable):
	_load_links = None

	@property
	def links_table_name(self):
		raise NotImplementedError

	def links(self):
		links = getattr(self, '_links', None)
		if links is None:
			if self._links_table_name is None:
				raise NotImplementedError(f"Table name {self.__class__.__name__} not set.")
			links = self._load_links(self.links_table_name, self.primary_key)
			setattr(self, '_links', links)
		return links

	def update_links(self, links: Iterable['Transaction']):
		existing = getattr(self, '_links', None)
		if existing is None:
			raise NotImplementedError(f"No links found for {self}.")
		self._links.extend([link for link in links if link not in existing])
