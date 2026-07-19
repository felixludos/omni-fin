"""German tax calculation scaffolding.

Future work: strict FIFO, investment-fund partial exemptions, and ETF
Vorabpauschale calculations.
"""

from __future__ import annotations

from collections.abc import Iterable

from omnifin.models import InvestmentSale, Transfer
from omnifin.tax.common import TaxResult


def calculate_german_tax(
    transfers: Iterable[Transfer], *, sales: Iterable[InvestmentSale] = (), tax_year: int
) -> TaxResult:
    sales_list = list(sales)
    transfers_list = list(transfers)
    result = TaxResult(jurisdiction="DE", tax_year=tax_year)
    result.sales_processed = len(sales_list)
    result.transfers_processed = len(transfers_list)
    result.warnings.append("German tax engine scaffold only; FIFO and Vorabpauschale not implemented yet.")
    return result
