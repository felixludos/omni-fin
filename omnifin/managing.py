import sqlite3
from datetime import datetime
from .misc import load_db


class FinanceManager:
	def __init__(self, db_path=None):
		self.conn = load_db(db_path)
		self.cursor = self.conn.cursor()
		self.current_report_id = None

	def _execute(self, query, params=()):
		self.cursor.execute(query, params)
		self.conn.commit()

	def close(self):
		self.conn.close()

	def get_table_properties(self, table_name):
		query = f"PRAGMA table_info({table_name})"
		self._execute(query)
		columns = self.cursor.fetchall()
		return columns

	# def get_account_info(self, account_name):


	def get_report_info(self, report_id):
		query = 'SELECT * FROM reports WHERE id = ?'
		self.cursor.execute(query, (report_id,))
		rid, date, cat, acc, desc, created = self.cursor.fetchone()


		return {
			'date': datetime.strptime(date, '%Y-%m-%d').date(),
			'category': cat,
			'associated_account': acc,
			'description': desc,
			'created_at': datetime.strptime(created, '%Y-%m-%d %H:%M:%S.%f'),
		}

	def generic_find(self, table, **props):
		query = f'SELECT * FROM {table} WHERE '
		query += ' AND '.join(f'{k} = ?' for k in props)
		self.cursor.execute(query, tuple(props.values()))
		return self.cursor.fetchall()

	def resolve_account(self, identifier):
		query = 'SELECT id FROM accounts WHERE account_name = ?'
		self.cursor.execute(query, (account_name,))
		return self.cursor.fetchone()

	def create_report(self, date, category, description=None, associated_account=None):
		if isinstance(date, datetime):
			date = date.strftime('%Y-%m-%d')
		query = '''
            INSERT INTO reports (dateof, category, associated_account, description, created_at)
            VALUES (?, ?, ?, ?, ?)
        '''
		self._execute(query, (date, category, associated_account, description, datetime.now()))
		return self.cursor.lastrowid

	def add_account(self, name, account_type, category, description=None, report_id=None):
		if report_id is None:
			report_id = self.create_report(date=datetime.now().date(), category="Account Creation")

		query = '''
            INSERT INTO accounts (account_name, account_type, category, description, report)
            VALUES (?, ?, ?, ?, ?)
        '''
		self._execute(query, (name, account_type, category, description, report_id))

	def remove_account(self, name):
		query = 'DELETE FROM accounts WHERE account_name = ?'
		self._execute(query, (name,))

	# Add similar methods for other tables like assets, transactions, etc.

	def get_accounts(self):
		self.cursor.execute('SELECT * FROM accounts')
		return self.cursor.fetchall()

# Add similar methods to retrieve data from other tables.

