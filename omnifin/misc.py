from pathlib import Path
# import sqlite3
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker



def load_db(path: Path | None = None):
	if path is not None and not path.exists():
		raise FileNotFoundError("Database file not found.")
	if path is None:
		path = Path('fin-tx.db')

	# Creating engine
	engine = create_engine(f'sqlite:///{path}')
	return engine



def db_session(engine: Engine):
	# Creating session
	Session = sessionmaker(bind=engine)
	session = Session()
	return session



def _old_load_db(path: Path | None = None):
	if path is not None and not path.exists():
		raise FileNotFoundError("Database file not found.")
	if path is None:
		path = Path('fin-tx.db')

	conn = sqlite3.connect(path)
	return conn
