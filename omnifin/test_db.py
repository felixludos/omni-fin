from .managing import FinanceManager


def test_create_report():
	m = FinanceManager()
	m.initialize()

	r = m.create_report(category='test')
	print(r)






