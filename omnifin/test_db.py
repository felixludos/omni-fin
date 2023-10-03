import omnifig as fig

from .managing import FinanceManager
from .datcls import Report
from . import misc



def _get_db_path():
	_root = misc.repo_root() / 'test' / 'tmp'
	_root.mkdir(exist_ok=True, parents=True)
	return _root / 'tmp_test.db'



def test_init_db():
	demo_root = misc.repo_root() / 'demo'

	fig.quick_run('init-db', 'demo',
				  path=_get_db_path(),
				  assets=demo_root / 'assets.yml',
				  accounts=demo_root / 'accounts.yml',
				  )



def test_create_report():
	# m = FinanceManager(_tmp_db)
	m = fig.create_config(_type='manager', path=_get_db_path()).pull()
	m.initialize()

	r = m.create_report(category='test')
	print(r)

	assert isinstance(r, Report), f'Expected Report, got {type(r)}'
	assert r.category == 'test', f'Expected category "test", got {r.category}'
	assert r.exists(), f'Expected report to exist, got {r.exists()}'
	assert r.is_loaded(), f'Expected report to be loaded, got {r.is_loaded()}'
	info = r.as_dict()
	assert info['category'] == 'test', f'Expected category "test", got {info["category"]}'
	assert 'created' in info, f'Expected "created" in info, got {info}'
	assert 'ID' in info, f'Expected "ID" in info, got {info}'
	assert info['description'] is None, f'Expected None, got {info["description"]}'
	assert info['account'] is None, f'Expected None, got {info["account"]}'



def test_clean_up():
	path = _get_db_path()
	root = path.parent
	if path.exists():
		path.unlink()
	root.rmdir()







