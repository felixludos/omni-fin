"""Shared tax calculation data structures."""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class TaxLot(BaseModel):
    """Tax lot used for gain/loss calculations in a jurisdiction-specific engine."""

    acquired_at: datetime = Field(description="Timezone-aware acquisition timestamp for the lot.")
    asset_symbol: str = Field(description="Symbol of the disposed asset (e.g., AAPL, BTC, VWCE).")
    quantity: float = Field(description="Disposed quantity from this lot.")
    basis_amount: float = Field(description="Total cost basis allocated to the disposed quantity.")
    basis_asset_symbol: str = Field(
        description="Unit/currency for basis_amount, usually the proceeds currency used for tax reporting."
    )


class TaxResult(BaseModel):
    """Output envelope returned by tax calculators and CLI/API responses."""

    jurisdiction: str = Field(description="Tax jurisdiction code, e.g. US or DE.")
    tax_year: int = Field(description="Calendar tax year for which calculation is run.")
    realized_gain: float = Field(default=0.0, description="Net realized capital gain in reporting currency.")
    ordinary_income: float = Field(default=0.0, description="Ordinary income amount recognized for tax year.")
    sales_processed: int = Field(default=0, description="Number of InvestmentSale rows consumed by the engine.")
    transfers_processed: int = Field(default=0, description="Number of Transfer rows consumed by the engine.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal caveats and missing-feature notices.")
