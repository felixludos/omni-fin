from typing import Optional, Union, Type, TypeVar, Any, Callable, Iterable, Mapping, Sequence, Tuple, List, Dict
import sqlite3
from datetime import datetime, date as datelike
from dateutil import parser



_known_record_types = {}



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
		return self.from_key(ID).load()

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
			if self._table_name is None:
				raise NotImplementedError(f"Table name for {self.__class__.__name__} not set.")
			if raw is None:
				raw = self._load_fn(self._table_name, self._primary_key)
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
		if self._table_name is None:
			raise NotImplementedError(f"Table name {self.__class__.__name__} not set.")
		for raw in self._fill_fn(self._table_name, self.as_dict()):
			yield self.from_raw(raw)




class Tagged(Fillable):
	_load_tags = None

	@property
	def tags_table_name(self):
		raise NotImplementedError

	def tags(self):
		tags = getattr(self, '_tags', None)
		if tags is None:
			if self._tags_table_name is None:
				raise NotImplementedError(f"Table name {self.__class__.__name__} not set.")
			tags = self._load_tags(self.tags_table_name, self.primary_key)
			setattr(self, '_tags', tags)
		return tags

	def update_tags(self, tags: Iterable['Tag']):
		existing = getattr(self, '_tags', None)
		if existing is None:
			raise NotImplementedError(f"No tags found for {self}.")
		self._tags.extend([tag for tag in tags if tag not in existing])



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


