from .imports import *

from .datacls import Report


def create_report(cfg: fig.Configuration, desc: str = None) -> Report:
	script_name = None
	if desc is None:
		script_name = cfg.pull('_meta.script_name', None, silent=True)
		if script_name is not None:
			desc = f'created for {script_name!r} script'

	report = Report(category=cfg.pull('category', script_name or 'default'),
					# account=cfg.pull('account', None),
					description=cfg.pull('description', None) if desc is None else desc)

	# cfg.print(f'Using report: {report}.')
	return report




