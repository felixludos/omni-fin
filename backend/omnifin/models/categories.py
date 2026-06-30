
from enum import Enum


class RowType(str, Enum):
	INTERNAL_TRANSFER = "internal_transfer"
	"""An internal transfer represents a movement of funds between two accounts that are both managed by this system."""

	EXTERNAL_TRANSFER = "external_transfer"
	"""An external transfer represents a movement of funds where only one of the accounts is managed by this system, the other is a third-party account (e.g., bank, brokerage, payment service, or merchant)."""

	BALANCE = "balance"
	"""A balance row represents the current balance of an account at a specific point in time. It is used to track the amount of funds available in an account, such as a bank account, investment account, or digital wallet."""

	TRADE = "trade"
	"""A trade row represents a transaction involving the buying or selling of financial instruments, such as stocks, bonds, options, or other securities. It includes details about the trade, such as the asset involved, the quantity, the price, and the date of the transaction."""

	CONVERSION = "conversion"
	"""A conversion row represents a transaction where one currency or asset is exchanged for another."""


class EventType(str, Enum):
	"""Canonical high-level event categories used by ingestion and AI-assisted labeling."""

	MULTI_TRANSFER = "multi_transfer"
	"""A multi-transfer event represents a series of transfers that should be considered jointly."""

	TRADE = "trade"
	"""A trade event represents the purchase or sale of an investment instrument."""

	TRANSFER = "transfer"
	"""A transfer event represents the movement of funds or assets between accounts. It includes details about the transfer, such as the source account, destination account, amount transferred, and any associated fees or costs."""

	CONVERSION = "conversion"
	"""A conversion event represents the exchange of one currency or asset for another. It includes details about the conversion, such as the original currency/asset, the target currency/asset, the conversion rate, and any associated fees or costs."""

	PROJECT = "project"
	"""A project event represents an event related to a specific project or initiative. It includes details about the project, such as the project name, description, start date, end date, and any associated costs or revenues."""

	OTHER = "other"
	"""An other event represents any event that does not fit into the predefined categories. It includes details about the event, such as a description, date, and any associated costs or revenues."""


class SaleTerm(str, Enum):
	"""Holding-period classification used for investment sales and tax computations."""

	SHORT = "short"
	"""Asset held for a short-term period under local tax rules."""

	LONG = "long"
	"""Asset held for a long-term period under local tax rules."""

	OTHER = "other"
	"""A known classification that is not strictly short or long in this schema."""

	UNKNOWN = "unknown"
	"""Insufficient information to determine holding period term."""


class AssetType(str, Enum):
	FIAT = "fiat"
	"""Fiat currencies such as USD, EUR, GBP, JPY, etc."""

	CURRENCY = "currency"
	"""Alias category for currency-like values where the source already uses this token."""

	EQUITY = "equity"
	"""Broad equity category used by broker exports and normalized DB rows."""

	STOCK = "stock"
	"""Direct shares in individual corporations (e.g., Apple, Microsoft, Amazon)."""

	BOND = "bond"
	"""Debt instruments issued by governments, municipalities, or corporations (e.g., US Treasury bonds, corporate bonds)."""

	CRYPTO = "crypto"
	"""Cryptocurrencies such as Bitcoin, Ethereum, and other digital assets."""

	ETF = "etf"
	"""Exchange-traded funds."""

	MUTUAL_FUND = "mutual_fund"
	"""Mutual funds."""

	FUND = "fund"
	"""Investment funds, including mutual funds, ETFs, and index funds."""

	CASH_EQUIVALENT = "cash_equivalent"
	"""Cash-like instruments, sweep balances, and money-market positions."""

	COMMODITY = "commodity"
	"""Commodity exposure instruments."""

	DERIVATIVE = "derivative"
	"""Derivative instruments such as options or futures."""
	
	OTHER = "other"
	"""Other asset categories that don't fit into the above classifications."""

	UNKNOWN = "unknown"
	"""Used when the asset category cannot be determined from the description."""


class EntityType(str, Enum):
	INDIVIDUAL = "individual"
	"""A single person, typically a natural person."""

	BUSINESS = "business"
	"""A legal entity that operates as a company, corporation, partnership, or other business organization."""

	LEGAL_ENTITY = "legal"
	"""A legal arrangement such as a trust, conservatorship, or estate that is recognized by law as having rights and responsibilities."""

	OTHER = "other"
	"""Other types of entities that don't fit into the above classifications."""

	UNKNOWN = "unknown"
	"""Used when the entity type cannot be determined from the description."""


class FundType(str, Enum):
	NA = "N/A"
	"""Not applicable or not a fund (e.g., stocks, bonds, options)."""

	ETF = "etf"
	"""Funds that are traded on stock exchanges and typically track an index (e.g., SPY, VOO)."""

	MUTUAL_FUND = "mutual_fund"
	"""Actively managed funds that are bought and sold at the end of the trading day at their net asset value (NAV)."""

	INDEX_FUND = "index_fund"
	"""Funds that passively track a specific market index (e.g., S&P 500) but are not traded on exchanges like ETFs."""

	REAL_ESTATE_FUND = "real_estate_fund"
	"""Funds that invest primarily in real estate assets or real estate companies."""

	OTHER_FUND = "other_fund"
	"""Other types of funds that don't fit into the above classifications."""


class FundEquityRatioType(str, Enum):
	NA = "N/A"
	"""Not applicable or not a fund (e.g., stocks, bonds, options)."""

	EQUITY_HEAVY = "equity_heavy"
	"""The fund's official prospectus mandates that it continuously holds more than 50% (i.e., 51%+) in physical corporate equities. Most broad U.S. index ETFs (like VOO, VTI, QQQ) fall into this category."""

	MIXED = "mixed"
	"""The fund continuously holds at least 25% in physical corporate equities (e.g., a balanced "60/40" stock-to-bond fund)."""

	OTHER_FUND = "other_fund"
	"""The fund holds less than 25% in equities (e.g., Treasury ETFs, bond funds, or money market funds)."""

	GERMAN_REAL_ESTATE_FUND = "german_real_estate_fund"
	"""The fund continuously invests at least 51% of its value in real estate or real estate companies which are primarily German. (Note: This applies to Real Estate Funds, not individual REIT shares)."""

	REAL_ESTATE_FUND = "real_estate_fund"
	"""The fund continuously invests at least 51% of its value in real estate or real estate companies which are primarily non-German. (Note: This applies to Real Estate Funds, not individual REIT shares)."""


class Country(str, Enum):
	US = "US"
	"""United States"""

	UK = "UK"
	"""United Kingdom"""

	# region Eurozone

	DE = "DE"
	"""Germany"""

	FR = "FR"
	"""France"""

	IT = "IT"
	"""Italy"""

	BE = "BE"
	"""Belgium"""

	NL = "NL"
	"""Netherlands"""

	LU = "LU"
	"""Luxembourg"""

	ES = "ES"
	"""Spain"""

	IE = "IE"
	"""Ireland"""

	AT = "AT"
	"""Austria"""

	FI = "FI"
	"""Finland"""

	GR = "GR"
	"""Greece"""

	#endregion

	VARIOUS = "various"
	"""Funds that invest in a mix of countries or global markets (e.g., global equity funds, international bond funds)."""

	OTHER = "other"
	"""Other countries"""


class AssetTagOptions(str, Enum):
	"""Canonical high-level tag categories used for labeling and organizing financial records."""

	GEOGRAPHIC = "geographic"
	"""Tags related to geographic locations, such as countries, regions, or cities."""

	SECTOR = "sector"
	"""Tags related to industry sectors or market segments."""

	STRATEGY = "strategy"
	"""Tags related to investment strategies or approaches."""

	OTHER = "other"
	"""Tags that do not fit into the predefined categories."""


class AccountTagOptions(str, Enum):
	"""Canonical high-level tag categories used for labeling and organizing financial accounts."""

	INCOME = "income"
	"""Tags related to income accounts, such as salary, dividends, or other sources of income."""

	EXPENSE = "expense"
	"""Tags related to expense accounts, such as bills, subscriptions, or other spending categories."""

	BANK_US = "bank_us"
	"""Tags related to US-based bank accounts."""

	BANK_EU = "bank_eu"
	"""Tags related to European-based bank accounts."""

	BROKERAGE = "brokerage"
	"""Tags related to brokerage accounts, such as stock trading or investment accounts."""

	RETIREMENT = "retirement"
	"""Tags related to retirement accounts, such as 401(k), IRA, or pension accounts."""

	HSA = "hsa"
	"""Tags related to Health Savings Accounts (HSA)."""

	CREDIT_CARD = "credit_card"
	"""Tags related to credit card accounts."""

	FINTECH = "fintech"
	"""Tags related to financial technology (fintech) accounts, such as digital wallets, payment apps, or online banking platforms."""

	OTHER = "other"
	"""Tags that do not fit into the predefined categories."""
