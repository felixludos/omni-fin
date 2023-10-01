import sqlite3
from dataclasses import dataclass


class SimpleRecord:
	_table_name = None
	@classmethod
	def from_id(cls, cursor: sqlite3.Cursor, ID: int):
		table = cls._table_name
		if table is None:
			raise NotImplementedError("Table name not set.")

		cursor.execute(f'SELECT * FROM {table} WHERE id = ?', (ID,))
		return cls(*cursor.fetchone())


@dataclass
class Account(SimpleRecord):
	name: str
	account_type: str
	category: str
	description: str
	report: Report





