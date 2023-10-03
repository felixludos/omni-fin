from typing import Optional, Union, Type, TypeVar, Any, Callable, Iterable, Mapping, Sequence, Tuple, List, Dict
import sqlite3
import omnifig as fig
from pathlib import Path
from datetime import datetime
from .building import init_db
from .datcls import init_loading, Record, Report, Account, Asset, Tag, Statement, Transaction, Tagged, Linked
from .misc import load_db



class ReportNotSetError(ValueError):
	pass


@fig.component('manager')
class FinanceManager(fig.Configurable):
	def __init__(self, path=None, root=None):
		if path is not None:
			path = Path(path)
		if root is not None:
			root = Path(root)
		if path is not None and root is not None:
			path = root / Path(path)
		self.path = path
		self.conn = load_db(path)
		self.cursor = self.conn.cursor()
		self.table_info = {}
		self.current_report = None

	def initialize(self):
		init_db(self.conn)
		init_loading(self.conn)

	def _execute(self, query, params=(), commit=True):
		self.cursor.execute(query, params)
		if commit:
			self.conn.commit()

	def close(self):
		self.conn.close()

	def get_table_properties(self, table_name):
		if table_name not in self.table_info:
			query = f"PRAGMA table_info({table_name})"
			self._execute(query)
			columns = self.cursor.fetchall()
			self.table_info[table_name] = columns
		return self.table_info[table_name]

	def generic_find(self, table, **props):
		query = f'SELECT * FROM {table} WHERE '
		query += ' AND '.join(f'{k} = ?' for k in props)
		self.cursor.execute(query, tuple(props.values()))
		return self.cursor.fetchall()

	def _format_raw_row(self, raw):
		return [val.primary_key if isinstance(val, Record) else val for val in raw]


	def _write_record(self, table, data, cols=None, *, commit=True):
		vals = self._format_raw_row(data)
		if cols is None:
			info = self.get_table_properties(table)
			cols = [name for (idx, name, typ, is_req, default, is_key) in info]
			if 'id' in cols:
				cols.remove('id')
		assert len(vals) == len(cols), f'Expected {len(cols)} values, got {len(vals)}'
		query = f'''INSERT INTO {table} ({", ".join(col for col in cols)}) VALUES ({", ".join("?" for _ in cols)})'''
		self._execute(query, vals, commit=commit)
		return self.cursor.lastrowid


	def write_report(self, report: Report):
		assert not report.exists(), f'Report {report} already exists'
		row = report.export_row()
		ID = self._write_record('reports', row, cols=['category', 'associated_account', 'description'])
		return report.set_ID(ID)


	def create_report(self, category: str = 'manual', account: Account | None = None, description: str = None):
		rep = Report(category=category, account=account, description=description)
		return self.write_report(rep)


	def create_current(self, category: str = 'manual', account: Account | None = None, description: str = None, *,
					   overwrite: bool = False):
		if self.current_report is None or overwrite:
			self.current_report = self.create_report(category, account, description)
		elif category != self.current_report.category \
			or account != self.current_report.account \
			or description != self.current_report.description:
			raise ValueError(f'Current report already exists: {self.current_report}')
		return self.current_report


	def write(self, record: Record, commit=True):
		assert not isinstance(record, Report), f'Use write_report to write reports'
		assert not record.exists(), f'Record {record} already exists'
		if self.current_report is None:
			raise ReportNotSetError
		table = record.table_name
		row = record.export_row(self.current_report)
		ID = self._write_record(table, row, commit=commit)
		return record.set_ID(ID)

	def write_all(self, records: Iterable[Record]):
		for record in records:
			self.write(record, commit=False)
		self.conn.commit()


	def get_accounts(self):
		yield from Account().fill()


	def get_assets(self):
		yield from Asset().fill()


	def add_tags(self, record: Tagged, *tags: Tag):
		assert record.exists(), f'Record {record} does not exist: {record}'
		if self.current_report is None:
			raise ReportNotSetError
		existing = set(record.tags())
		new = [tag for tag in tags if tag not in existing]
		if not len(new):
			return
		assert all(tag.exists() for tag in new), f'Not all tags exist: {[tag for tag in new if not tag.exists()]}'
		table = record.tags_table_name

		for tag in new:
			query = f'INSERT INTO {table} (id, tag_id, report) VALUES (?, ?, ?)'
			self.cursor.execute(query, (tag.primary_key, record.primary_key, self.current_report.primary_key))
		self.conn.commit()
		record.update_tags(new)
		return record


	def add_links(self, record: Linked, *links: Linked):
		assert record.exists(), f'Record {record} does not exist: {record}'
		if self.current_report is None:
			raise ReportNotSetError
		existing = set(record.links())
		new = [link for link in links if link not in existing]
		if not len(new):
			return
		assert all(link.exists() for link in new), f'Not all links exist: {[link for link in new if not link.exists()]}'
		table = record.links_table_name

		for link in new:
			query = f'INSERT INTO {table} (id1, id2, report) VALUES (?, ?, ?)'
			self.cursor.execute(query, (min(record.primary_key, link.primary_key),
										max(record.primary_key, link.primary_key),
										self.current_report.primary_key))
		self.conn.commit()
		record.update_links(new)
		return record


	def link_all(self, *records: Record):
		for i in range(len(records)-1):
			self.add_links(records[i], *records[i+1:])


