from omnibelt import unspecified_argument
import omnifig as fig
from functools import cached_property
from .managing import FinanceManager
from .datcls import Asset, Account, Tag


@fig.component('id')
class Identifier:
	_manager: FinanceManager = None
	def __init__(self, raw: str):
		self.raw = raw
		self.fixed = unspecified_argument


	@cached_property
	def is_known(self):
		if self.fixed is unspecified_argument and self._manager is not None:
			self.fixed = self._manager.p(self.raw)
		return self.fixed is not unspecified_argument and self.fixed is not None


	def __str__(self):
		return self.fixed if self.is_known else self.raw


	def __repr__(self):
		if self.is_known:
			return f'{self.fixed}'
		return f'{self.raw!r}[unknown]'



class UnknownAssetError(KeyError):
	pass



class UnknownAccountError(KeyError):
	pass



@fig.component('world')
class World(fig.Configurable):
	def __init__(self, asset_shortcuts=None, account_shortcuts=None):
		self.asset_shortcuts = asset_shortcuts or {}
		self.account_shortcuts = account_shortcuts or {}


	def populate(self, manager: FinanceManager = None):
		self.assets_raw = list(Asset().fill())
		self.assets = {a.name: a for a in self.assets_raw}
		self.asset_shortcuts.update({self.standardize(a.name): a.name for a in self.assets_raw})
		assert len(self.assets) == len(self.assets_raw), 'Duplicate assets found.'
		missing_assets = [val for val in self.asset_shortcuts.values() if val not in self.assets]
		assert not len(missing_assets), f'Missing assets: {missing_assets}'

		self.accounts_raw = list(Account().fill())
		self.accounts = {a.name: a for a in self.accounts_raw}
		self.account_shortcuts.update({self.standardize(a.name): a.name for a in self.accounts_raw})
		assert len(self.accounts) == len(self.accounts_raw), 'Duplicate accounts found.'
		missing_accounts = [val for val in self.account_shortcuts.values() if val not in self.accounts]
		assert not len(missing_accounts), f'Missing accounts: {missing_accounts}'


	@staticmethod
	def standardize(raw):
		s = (raw.replace(',', ' ').replace('.', ' ').replace(';', ' ').replace('-', ' ')
			 .replace('_', ' ').replace('/', ' ').strip().lower())
		s = ' '.join(t.strip() for t in s.split() if len(t))
		return s


	def find_asset(self, raw: str):
		name = self.standardize(raw)
		if name in self.assets:
			return self.assets[name]
		if name in self.asset_shortcuts:
			return self.assets[self.asset_shortcuts[name]]
		raise UnknownAssetError(name)


	def find_account(self, raw: str):
		name = self.standardize(raw)
		if name in self.accounts:
			return self.accounts[name]
		if name in self.account_shortcuts:
			return self.accounts[self.account_shortcuts[name]]
		raise UnknownAccountError(name)


