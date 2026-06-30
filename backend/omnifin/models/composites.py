
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from omnifin.models.categories import EventType, SaleTerm
from omnifin.models.domain import Asset, Investment, Statement, Transfer


class Portfolio(BaseModel):
	"""Portfolio snapshot represented by the statements that compose it."""

	model_config = ConfigDict(
		title='Portfolio',
		extra='forbid',
		json_schema_extra={
			'example': {
				'components': [
					{
						'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24f72',
						'date': '2026-01-31T00:00:00Z',
						'account': {'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24f11', 'name': 'Brokerage'},
						'unit': {'symbol': 'USD'},
						'balance': 12500.21,
					},
				],
			},
		},
	)

	components: list[Statement] = Field(
		default_factory=list,
		description='Statements that jointly represent the holdings and cash balances for the portfolio snapshot.',
	)


class Trade(BaseModel):
	"""High-level trade abstraction built from the transfer pair that forms the economic exchange."""

	model_config = ConfigDict(
		title='Trade',
		extra='forbid',
		json_schema_extra={
			'example': {
				'event_type': 'trade',
				'sending': {
					'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24a01',
					'unit': {'symbol': 'AAPL'},
					'amount': 10.0,
				},
				'receiving': {
					'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24a02',
					'unit': {'symbol': 'USD'},
					'amount': 2250.0,
				},
			},
		},
	)

	event_type: EventType = Field(
		default=EventType.TRADE,
		description='Canonical event type for this composite. Keep as trade when representing buy/sell activity.',
	)
	sending: Transfer = Field(
		description='Transfer representing the quantity/value that leaves the source side of the trade.',
	)
	receiving: Transfer = Field(
		description='Transfer representing the quantity/value received as consideration in the trade.',
	)

	@model_validator(mode='after')
	def _validate_trade_components(self) -> 'Trade':
		if self.sending.id == self.receiving.id:
			raise ValueError('sending and receiving transfers must be different transfer records')
		return self


class Sale(Trade):
	"""Trade specialization for taxable disposals with lot and term metadata."""

	model_config = ConfigDict(
		title='Sale',
		extra='forbid',
		json_schema_extra={
			'example': {
				'event_type': 'trade',
				'sending': {
					'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24b01',
					'unit': {'symbol': 'VWCE'},
					'amount': 5.0,
				},
				'receiving': {
					'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24b02',
					'unit': {'symbol': 'EUR'},
					'amount': 612.2,
				},
				'fee': {
					'id': '018f6f12-7e09-7f2f-8f84-c0f2d7d24b03',
					'unit': {'symbol': 'EUR'},
					'amount': 1.2,
				},
				'acquisition_date': '2024-02-14T00:00:00Z',
				'cost_basis': 500.0,
				'term': 'long',
			},
		},
	)

	fee: Optional[Transfer] = Field(
		default=None,
		description='Optional fee transfer charged for execution or settlement of the sale.',
	)
	acquisition: Optional[Transfer] = Field(
		default=None,
		description='Transfer that originally acquired the sold lot. Use when historical source transaction is known.',
	)
	acquisition_date: Optional[datetime] = Field(
		default=None,
		description='Acquisition date of the sold lot. Required when precise holding-period classification is expected.',
	)
	cost_basis: Optional[float] = Field(
		default=None,
		ge=0,
		description='Total tax basis for the disposed lot in the same currency/unit as proceeds.',
	)
	term: SaleTerm = Field(
		default=SaleTerm.SHORT,
		description='Holding-period term used for jurisdictional tax treatment.',
	)

	@model_validator(mode='after')
	def _validate_sale_context(self) -> 'Sale':
		if self.cost_basis is not None and self.cost_basis < 0:
			raise ValueError('cost_basis must be non-negative')
		if self.acquisition is not None and self.acquisition_date is None:
			raise ValueError('acquisition_date must be provided when acquisition transfer is present')
		return self



class ParsingResult(BaseModel):
	summary: str
	confidence: float = Field(..., ge=0.0, le=1.0)
	objects: list[Transfer | Trade | Sale | Asset | Investment]

