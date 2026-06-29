"""US tax calculation scaffolding.

Future work: FIFO/LIFO lot selection, wash-sale windows across accounts, and
short-term versus long-term holding-period classification.
"""

from __future__ import annotations

from collections.abc import Iterable

from omnifin.models import InvestmentSale, Transfer
from omnifin.tax.common import TaxResult


def calculate_us_tax(
    transfers: Iterable[Transfer], *, sales: Iterable[InvestmentSale] = (), tax_year: int
) -> TaxResult:
    sales_list = list(sales)
    transfers_list = list(transfers)
    result = TaxResult(jurisdiction="US", tax_year=tax_year)
    result.sales_processed = len(sales_list)
    result.transfers_processed = len(transfers_list)
    result.warnings.append("US tax engine scaffold only; lot matching not implemented yet.")
    return result
