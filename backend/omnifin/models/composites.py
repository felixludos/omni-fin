
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any, Iterable, Literal, Optional, Self
from uuid import UUID
import sqlite3
import weakref

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from omnifin.models.domain import Statement, Transfer


class Portfolio(BaseModel):
	components: list[Statement] = Field(default_factory=list, description='The list of statements that make up the portfolio.')


class Trade(BaseModel): # stored as an "event"
	sending: Transfer
	receiving: Transfer


class Sale(Trade):
	fee: Optional[Transfer] = None
	acquisition: Optional[Transfer] = Field(default=None, description='The transfer representing the acquisition of the asset being sold (if present in dataset).')
	acquisition_date: datetime = Field(default=None, description='The date the asset being sold was acquired.')
	cost_basis: Optional[float] = Field(default=None, description='The cost basis of the asset being sold, must use the same asset type as the receiving transfer (proceeds).')
	term: Literal['short', 'long'] = Field(default='short', description='The term of the sale, either short or long.')
