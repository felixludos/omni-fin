"""Shared tax calculation data structures."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class TaxLot(BaseModel):
    acquired_at: datetime
    asset_symbol: str
    quantity: float
    basis_amount: float
    basis_asset_symbol: str


class TaxResult(BaseModel):
    jurisdiction: str
    tax_year: int
    realized_gain: float = 0.0
    ordinary_income: float = 0.0
    warnings: list[str] = Field(default_factory=list)
