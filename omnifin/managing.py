from sqlalchemy import create_engine, Column, Integer, String, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

from .building import Base, Report, Account, Asset, Transaction

# Database Manager Class
class FinanceManager:
	def __init__(self, db_url):
		self.engine = create_engine(db_url)
		self.Session = sessionmaker(bind=self.engine)
		Base.metadata.create_all(self.engine)

	def add_report(self, date, category, description=None):
		session = self.Session()
		report = Report(dateof=date, category=category, description=description)
		session.add(report)
		session.commit()
		return report

	def add_account(self, name, account_type, category, description=None):
		session = self.Session()
		account = Account(account_name=name, account_type=account_type, category=category, description=description)
		session.add(account)
		session.commit()

	def add_asset(self, name, category, description=None):
		session = self.Session()
		asset = Asset(asset_name=name, category=category, description=description)
		session.add(asset)
		session.commit()

	def add_transaction(self, date, description, quantity, received_amount, sender, receiver):
		session = self.Session()
		transaction = Transaction(dateof=date, description=description, quantity=quantity,
								  received_amount=received_amount, sender=sender, receiver=receiver)
		session.add(transaction)
		session.commit()

	# Add other methods for removing and retrieving records as needed



