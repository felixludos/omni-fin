"""German tax calculation scaffolding.

Future work: strict FIFO, investment-fund partial exemptions, and ETF
Vorabpauschale calculations.
"""

from __future__ import annotations

from collections.abc import Iterable

from omnifin.models import Transfer
from omnifin.tax.common import TaxResult


def calculate_german_tax(transfers: Iterable[Transfer], *, tax_year: int) -> TaxResult:
    result = TaxResult(jurisdiction="DE", tax_year=tax_year)
    result.warnings.append("German tax engine scaffold only; FIFO and Vorabpauschale not implemented yet.")
    return result
