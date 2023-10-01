from sqlalchemy import (Column, Integer, String, Date, Float, ForeignKey,
						DateTime, create_engine, UniqueConstraint, Index)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func

Base = declarative_base()


class Report(Base):
	__tablename__ = 'reports'

	id = Column(Integer, primary_key=True, autoincrement=True)
	dateof = Column(Date, nullable=False)
	category = Column(String, nullable=False)
	associated_account = Column(Integer, ForeignKey('accounts.id'))
	description = Column(String)
	created_at = Column(DateTime, default=func.current_timestamp())


class Asset(Base):
	__tablename__ = 'assets'

	id = Column(Integer, primary_key=True, autoincrement=True)
	asset_name = Column(String, nullable=False)
	category = Column(String, nullable=False)
	description = Column(String)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class Account(Base):
	__tablename__ = 'accounts'

	id = Column(Integer, primary_key=True, autoincrement=True)
	account_name = Column(String, nullable=False)
	account_type = Column(String, nullable=False)
	category = Column(String, nullable=False)
	description = Column(String)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class Tag(Base):
	__tablename__ = 'tags'

	tag_id = Column(Integer, primary_key=True, autoincrement=True)
	tag_name = Column(String, nullable=False, unique=True)
	description = Column(String)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class TransactionTag(Base):
	__tablename__ = 'transaction_tags'

	transaction_id = Column(Integer, ForeignKey('transactions.id'), primary_key=True)
	tag_id = Column(Integer, ForeignKey('tags.tag_id'), primary_key=True)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class StatementTag(Base):
	__tablename__ = 'statement_tags'

	statement_id = Column(Integer, ForeignKey('statements.id'), primary_key=True)
	tag_id = Column(Integer, ForeignKey('tags.tag_id'), primary_key=True)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class AccountTag(Base):
	__tablename__ = 'account_tags'

	account_id = Column(Integer, ForeignKey('accounts.id'), primary_key=True)
	tag_id = Column(Integer, ForeignKey('tags.tag_id'), primary_key=True)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class Statement(Base):
	__tablename__ = 'statements'

	id = Column(Integer, primary_key=True, autoincrement=True)
	dateof = Column(Date, nullable=False)
	account = Column(Integer, ForeignKey('accounts.id'), nullable=False)
	balance = Column(Float, nullable=False)
	unit = Column(Integer, ForeignKey('assets.id'), nullable=False)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class Transaction(Base):
	__tablename__ = 'transactions'

	id = Column(Integer, primary_key=True, autoincrement=True)
	dateof = Column(Date, nullable=False)
	description = Column(String)
	quantity = Column(Float, nullable=False)
	unit = Column(Integer, ForeignKey('assets.id'), nullable=False)
	received_amount = Column(Float)
	received_unit = Column(Integer, ForeignKey('assets.id'))
	sender = Column(Integer, ForeignKey('accounts.id'), nullable=False)
	receiver = Column(Integer, ForeignKey('accounts.id'), nullable=False)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)


class Link(Base):
	__tablename__ = 'links'

	id = Column(Integer, primary_key=True, autoincrement=True)
	transaction1 = Column(Integer, ForeignKey('transactions.id'), nullable=False)
	transaction2 = Column(Integer, ForeignKey('transactions.id'), nullable=False)
	link_type = Column(String)
	report = Column(Integer, ForeignKey('reports.id'), nullable=False)

	__table_args__ = (UniqueConstraint('transaction1', 'transaction2', name='uix_transaction_links'),)


# Indexes
Index('idx_reports_dateof', Report.dateof)
Index('idx_transactions_dateof', Transaction.dateof)

# Create an engine and bind it to the session
engine = create_engine('sqlite:///your-database-name.db')
Session = sessionmaker(bind=engine)

# Create all tables
Base.metadata.create_all(engine)


# Function to initialize db
def init_db(engine):
	# engine = create_engine('sqlite:///your-database-name.db')  # use your database URL here
	Base.metadata.create_all(engine)

	Index('idx_reports_dateof', Report.dateof)
	Index('idx_transactions_dateof', Transaction.dateof)

