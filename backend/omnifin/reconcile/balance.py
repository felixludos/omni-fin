"""Statement reconciliation helpers."""

from __future__ import annotations

from pydantic import BaseModel

from omnifin.models import Statement


class BalanceCheck(BaseModel):
    statement_id: str
    expected_balance: float
    observed_balance: float
    difference: float
    is_balanced: bool


def check_statement_balance(statement: Statement, observed_balance: float, *, tolerance: float = 0.01) -> BalanceCheck:
    expected = float(statement.balance or 0.0)
    difference = observed_balance - expected
    return BalanceCheck(
        statement_id=str(statement.id),
        expected_balance=expected,
        observed_balance=observed_balance,
        difference=difference,
        is_balanced=abs(difference) <= tolerance,
    )
