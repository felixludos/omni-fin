from omnibelt import unspecified_argument
import omnifig as fig
from functools import cached_property
from .managing import FinanceManager



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




