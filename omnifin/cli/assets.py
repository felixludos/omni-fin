"""``fin assets`` — Detect and parse investments from a transaction CSV using LLM."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

import click
from pydantic import BaseModel, Field
from rich.console import Console

from omnifin.ai.structured import LLMProvider
from omnifin.core.db import DatabaseSession
from omnifin.core.ids import stable_hash_bytes, utcnow
from omnifin.models import Asset, Comment, Investment, Report, Tag
from omnifin.models.categories import AssetType, Country, FundFocus, FundType

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_PATH = REPO_ROOT / "assets" / "asset_parse_prompt.md"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ParsedAsset(BaseModel):
    """Investment metadata extracted by the LLM for a single row."""

    active: bool = Field(
        default=False,
        description=(
            "Whether this row references a financial security or investment instrument. "
            "True for stocks, ETFs, mutual funds, bonds, crypto, etc. "
            "False for pure cash transactions like dividends, fees, transfers."
        ),
    )
    symbol: str | None = Field(
        default=None,
        description=(
            "Canonical uppercase ticker or identifier used as the primary key. "
            "Examples: 'AAPL' (Apple), 'VWCE' (Vanguard FTSE All-World), 'BTC' (Bitcoin). "
            "Must be uppercase, no spaces."
        ),
    )
    name: str | None = Field(
        default=None,
        description=(
            "Human-readable security name. Use the common brand name, not legal names. "
            "Examples: 'Apple', 'Microsoft', 'Vanguard Total Stock Market ETF'. "
            "Remove suffixes like 'Common Stock', 'Ordinary Shares', 'Class A'."
        ),
    )
    category: AssetType | None = Field(
        default=None,
        description=(
            "Asset type classification. Allowed values: "
            "'stock' (individual company shares), 'etf' (exchange-traded fund), "
            "'mutual_fund' (actively managed fund), 'index_fund' (passively tracked, not on exchange), "
            "'bond' (government or corporate bonds), 'crypto' (cryptocurrencies), "
            "'commodity' (commodity exposure), 'derivative' (options, futures), "
            "'cash_equivalent' (money market, sweep balances), 'fiat' (currency like USD, EUR), "
            "'other', 'unknown'."
        ),
    )
    nyse_ticker: str | None = Field(
        default=None,
        description=(
            "NYSE-format ticker symbol if different from the main symbol. "
            "Example: 'BRK/B' for Berkshire Hathaway (when main symbol is 'BRK.B')."
        ),
    )
    ibkr_ticker: str | None = Field(
        default=None,
        description=(
            "Interactive Brokers platform ticker identifier. "
            "Example: 'AAPL', 'ISIN:IE00BK5BQT80' for some international securities."
        ),
    )
    identifier: str | None = Field(
        default=None,
        description=(
            "Stable instrument identifier (ISIN, CUSIP, WKN, SEDOL, FIGI). "
            "ISIN example: 'US0378331005' (AAPL). "
            "CUSIP example: '037833100' (AAPL)."
        ),
    )
    identifier_type: str | None = Field(
        default=None,
        description=(
            "Type of the identifier field. Allowed values: 'isin', 'cusip', 'wkn', 'sedol', 'figi'."
        ),
    )
    country: Country | None = Field(
        default=None,
        description=(
            "Primary domicile country code of the issuer. "
            "Common values: 'US' (United States), 'IE' (Ireland), 'DE' (Germany), "
            "'UK' (United Kingdom), 'NL' (Netherlands), 'LU' (Luxembourg), "
            "'FR' (France), 'CH' (Switzerland), 'JP' (Japan), "
            "'various' (global/multi-country funds)."
        ),
    )
    fund_type: FundType | None = Field(
        default=None,
        description=(
            "Fund structure classification. Allowed values: "
            "'N/A' (not a fund — stocks, bonds, crypto, etc.), "
            "'etf' (exchange-traded fund), 'mutual_fund' (actively managed), "
            "'index_fund' (passively tracked, not on exchange), "
            "'real_estate_fund' (REIT or real estate fund), 'other_fund'."
        ),
    )
    fund_focus: FundFocus | None = Field(
        default=None,
        description=(
            "Fund equity/real-estate exposure bucket for jurisdiction-specific tax treatment. "
            "Allowed values: 'N/A' (not a fund), "
            "'equity_heavy' (>50% in corporate equities, e.g. VOO, VTI, QQQ), "
            "'mixed' (25-50% in equities, balanced funds), "
            "'other_fund' (<25% in equities, bond funds, Treasury ETFs), "
            "'german_real_estate_fund' (>=51% German real estate), "
            "'real_estate_fund' (>=51% non-German real estate)."
        ),
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in this parse result, from 0.0 to 1.0.",
    )
    summary: str = Field(
        default="",
        description="One-line human-readable description of what this row represents.",
    )


class AutoParser(BaseModel):
    """Specifies a column/value pair that can auto-match similar rows."""

    column: str = Field(
        description=(
            "CSV column name to match on (e.g., 'Symbol', 'Symbol(CUSIP)'). "
            "Must be an exact match to a header in the input CSV."
        ),
    )
    value: str = Field(
        description=(
            "Exact text value in that column that identifies the same investment. "
            "All rows where this column contains this exact string will be auto-filled."
        ),
    )


class LlmAssetResponse(BaseModel):
    """Full LLM response schema for structured investment parsing."""

    summary: str = Field(
        default="",
        description="One-line human-readable description of what this row represents.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in this parse result, from 0.0 to 1.0.",
    )
    active: bool = Field(
        default=False,
        description=(
            "Whether this row references a financial security or investment instrument. "
            "True for stocks, ETFs, mutual funds, bonds, crypto, etc. "
            "False for pure cash transactions (dividends, fees, transfers) or unparseable rows."
        ),
    )
    investment: ParsedAsset | None = Field(
        default=None,
        description=(
            "Investment metadata when active=true. Must include at least 'active: true' and 'symbol'. "
            "Set to null when active=false."
        ),
    )
    auto_parse: AutoParser | None = Field(
        default=None,
        description=(
            "Optional: speeds up processing by auto-filling all rows where a given column "
            "matches a specific value. Set this when you can identify a column that uniquely "
            "identifies the same security across multiple rows. Leave null if no such column exists."
        ),
    )


class RowResult(BaseModel):
    """Per-row result stored during processing."""

    index: int
    source_row: dict[str, str]
    row_hash: str
    selected: bool = True
    parsed: LlmAssetResponse | None = None
    from_partial: bool = False


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------


def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _row_hash(row: dict[str, str]) -> str:
    return stable_hash_bytes(json.dumps(row, sort_keys=True, ensure_ascii=False)).hex()


def _load_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    import io

    text = _strip_bom(path.read_text(encoding="utf-8"))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        click.echo("Error: CSV has no header row.", err=True)
        raise SystemExit(1)
    headers = list(reader.fieldnames)
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({k: ("" if v is None else str(v)) for k, v in raw.items()})
    return headers, rows


_ENUM_VALUE_MAP: dict[str, str] = {
    **{m.name: m.value for m in AssetType},
    **{m.name: m.value for m in Country},
    **{m.name: m.value for m in FundType},
    **{m.name: m.value for m in FundFocus},
}


def _norm_enum_str(val: str | None) -> str | None:
    """Normalize ``'EnumType.MEMBER'`` → the enum's string value for backwards-compatible partial loading."""
    if not val:
        return None
    if "." in val and val.split(".", 1)[0].isidentifier():
        member_name = val.split(".", 1)[1]
        return _ENUM_VALUE_MAP.get(member_name, member_name)
    return val


def _load_partial(path: Path) -> dict[str, LlmAssetResponse]:
    """Load a partial/progress CSV and return {row_hash: parsed_response}."""
    import io

    text = _strip_bom(path.read_text(encoding="utf-8"))
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return {}

    results: dict[str, LlmAssetResponse] = {}
    for row in reader:
        row_hash = row.get("row_hash", "")
        if not row_hash:
            continue
        active_str = row.get("active", "")
        if active_str == "":
            continue
        active = active_str.lower() in ("true", "1", "yes")
        parsed = LlmAssetResponse(
            summary=row.get("summary", ""),
            confidence=float(row.get("confidence", "0") or "0"),
            active=active,
            investment=(
                ParsedAsset(
                    active=active,
                    symbol=row.get("symbol") or None,
                    name=row.get("name") or None,
                    category=_norm_enum_str(row.get("category")),
                    nyse_ticker=row.get("nyse_ticker") or None,
                    ibkr_ticker=row.get("ibkr_ticker") or None,
                    identifier=row.get("identifier") or None,
                    identifier_type=row.get("identifier_type") or None,
                    country=_norm_enum_str(row.get("country")),
                    fund_type=_norm_enum_str(row.get("fund_type")),
                    fund_focus=_norm_enum_str(row.get("fund_focus")),
                    confidence=float(row.get("confidence", "0") or "0"),
                    summary=row.get("summary", ""),
                )
                if active
                else None
            ),
        )
        results[row_hash] = parsed
    return results


# ---------------------------------------------------------------------------
# Auto-fill helpers
# ---------------------------------------------------------------------------


def _auto_fill_rows(
    results: list[RowResult],
    parsed: LlmAssetResponse,
    headers: list[str] | None,
    progress_writer: ProgressWriter | None,
) -> int:
    """Fill all unprocessed rows matching auto_parse column/value.

    Returns the number of rows auto-filled.
    """
    if not parsed.auto_parse:
        return 0
    col = parsed.auto_parse.column
    val = parsed.auto_parse.value
    if headers is not None and col not in headers:
        return 0

    filled = 0
    for r in results:
        if r.parsed is not None:
            continue
        if r.source_row.get(col, "") == val:
            r.parsed = parsed
            if progress_writer:
                progress_writer.write_row(r)
            filled += 1
    return filled


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _build_prompt(row: dict[str, str], existing_symbols: list[str]) -> str:
    if PROMPT_TEMPLATE_PATH.exists():
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = _fallback_prompt()

    schema = json.dumps(LlmAssetResponse.model_json_schema(), indent=2)
    replacements = {
        "row_json": json.dumps(row, ensure_ascii=False, indent=2),
        "existing_symbols_json": json.dumps(existing_symbols, ensure_ascii=False),
        "schema_json": schema,
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _fallback_prompt() -> str:
    return (
        "You are an investment security detector.\n"
        "Examine the input row and determine if it references a financial security.\n"
        'Return JSON: {"summary": "...", "confidence": 0.0-1.0, "active": bool, '
        '"investment": {"active": true, "symbol": "...", ...} or null}\n'
        "Row: {{row_json}}\n"
        "Existing symbols: {{existing_symbols_json}}"
    )


# ---------------------------------------------------------------------------
# Database writing
# ---------------------------------------------------------------------------


def _load_existing_symbols(db_path: str) -> list[str]:
    try:
        with DatabaseSession(db_path) as session:
            symbols: list[str] = []
            for asset in session.all(Asset, limit=10000):
                if asset.symbol:
                    symbols.append(asset.symbol.upper())
            return sorted(set(symbols))
    except Exception:
        return []


def _build_investment_objects(
    *,
    session: DatabaseSession,
    parsed: LlmAssetResponse,
    investments_by_symbol: dict[str, Investment],
) -> list[Any]:
    """Build Investment domain objects from a parsed LLM response."""
    out: list[Any] = []
    if not parsed.active or parsed.investment is None:
        return out

    inv = parsed.investment
    symbol = (inv.symbol or "").strip().upper()
    if not symbol:
        return out

    if symbol in investments_by_symbol:
        return out

    created = Investment(_session=session, symbol=symbol)
    investments_by_symbol[symbol] = created

    if inv.name:
        created.name = inv.name
    if inv.category:
        created.category = inv.category

    if inv.nyse_ticker:
        created.comment(
            Comment(
                _session=session,
                content=inv.nyse_ticker,
                type="nyse_ticker",
                created_at=utcnow(),
            )
        )
    if inv.ibkr_ticker:
        created.comment(
            Comment(
                _session=session,
                content=inv.ibkr_ticker,
                type="ibkr_ticker",
                created_at=utcnow(),
            )
        )
    if inv.identifier:
        created.comment(
            Comment(
                _session=session,
                content=inv.identifier,
                type="asset_identifier",
                created_at=utcnow(),
            )
        )

    if inv.identifier_type:
        created.add_tags(
            Tag(_session=session, name=inv.identifier_type, category="asset_identifier_type")
        )
    if inv.country:
        created.add_tags(Tag(_session=session, name=inv.country, category="country"))
    if inv.fund_type:
        created.add_tags(Tag(_session=session, name=inv.fund_type, category="fund_type"))
    if inv.fund_focus:
        created.add_tags(Tag(_session=session, name=inv.fund_focus, category="fund_focus"))

    out.append(created)
    return out


# ---------------------------------------------------------------------------
# Progress CSV output
# ---------------------------------------------------------------------------

# Column order for the parsed fields section of the progress CSV.
_PARSED_FIELDS = [
    "active",
    "symbol",
    "name",
    "category",
    "nyse_ticker",
    "ibkr_ticker",
    "identifier",
    "identifier_type",
    "country",
    "fund_type",
    "fund_focus",
    "confidence",
    "summary",
]


def _result_to_csv_row(
    r: RowResult,
    out_fields: list[str],
    source_headers: list[str],
    *,
    parsed_only: bool = False,
) -> dict[str, Any]:
    """Convert a RowResult into a flat dict suitable for DictWriter."""
    row: dict[str, Any] = {}
    if not parsed_only:
        for h in source_headers:
            row[h] = r.source_row.get(h, "")
    row["row_hash"] = r.row_hash
    if r.parsed:
        row["active"] = str(r.parsed.active)
        if r.parsed.investment:
            inv = r.parsed.investment
            row["symbol"] = inv.symbol or ""
            row["name"] = inv.name or ""
            row["category"] = inv.category.value if inv.category else ""
            row["nyse_ticker"] = inv.nyse_ticker or ""
            row["ibkr_ticker"] = inv.ibkr_ticker or ""
            row["identifier"] = inv.identifier or ""
            row["identifier_type"] = inv.identifier_type or ""
            row["country"] = inv.country.value if inv.country else ""
            row["fund_type"] = inv.fund_type.value if inv.fund_type else ""
            row["fund_focus"] = inv.fund_focus.value if inv.fund_focus else ""
            row["confidence"] = str(inv.confidence)
            row["summary"] = r.parsed.summary
        else:
            row["confidence"] = str(r.parsed.confidence)
            row["summary"] = r.parsed.summary
    else:
        row["active"] = "false"
    return row


class ProgressWriter:
    """Writes the progress CSV row-by-row, flushing after each write for crash safety."""

    def __init__(self, path: Path, source_headers: list[str], parsed_only: bool = False) -> None:
        self._source_headers = source_headers
        self._parsed_only = parsed_only
        out_fields = list(source_headers) if not parsed_only else []
        out_fields.extend(["row_hash"] + _PARSED_FIELDS)
        self._out_fields = out_fields
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("w", encoding="utf-8", newline="")
        self._writer = csv.DictWriter(self._fh, fieldnames=out_fields, extrasaction="ignore")
        self._writer.writeheader()
        self._fh.flush()

    def write_row(self, result: RowResult) -> None:
        """Append one row and flush to disk immediately."""
        row = _result_to_csv_row(
            result, self._out_fields, self._source_headers, parsed_only=self._parsed_only
        )
        self._writer.writerow(row)
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


def _write_progress_csv(
    path: Path,
    source_headers: list[str],
    results: list[RowResult],
    *,
    parsed_only: bool = False,
) -> None:
    """Bulk-write the progress CSV (used as a fallback; prefer ProgressWriter)."""
    out_fields = list(source_headers) if not parsed_only else []
    out_fields.extend(["row_hash"] + _PARSED_FIELDS)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(
                _result_to_csv_row(r, out_fields, source_headers, parsed_only=parsed_only)
            )


# ---------------------------------------------------------------------------
# Interactive mode (rich TUI)
# ---------------------------------------------------------------------------

_EDITABLE_FIELDS = frozenset(
    {
        "symbol",
        "name",
        "category",
        "country",
        "fund_type",
        "fund_focus",
        "identifier",
        "identifier_type",
        "nyse_ticker",
        "ibkr_ticker",
    }
)


def _display_parsed_table(console: "Console", parsed: LlmAssetResponse) -> None:
    """Display the parsed investment result as a rich table."""
    from rich.panel import Panel
    from rich.table import Table as _Table

    if parsed and parsed.active and parsed.investment:
        inv = parsed.investment
        table = _Table(title="Parsed Investment", show_header=False, border_style="green")
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("Symbol", inv.symbol or "-")
        table.add_row("Name", inv.name or "-")
        table.add_row("Category", inv.category or "-")
        table.add_row("Country", inv.country or "-")
        table.add_row("Fund Type", inv.fund_type or "-")
        table.add_row("Fund Focus", inv.fund_focus or "-")
        table.add_row("ISIN/CUSIP", inv.identifier or "-")
        table.add_row("ID Type", inv.identifier_type or "-")
        table.add_row("NYSE Ticker", inv.nyse_ticker or "-")
        table.add_row("IBKR Ticker", inv.ibkr_ticker or "-")
        table.add_row("Confidence", f"{parsed.confidence:.0%}")
        table.add_row("Summary", parsed.summary)
        console.print(table)
    elif parsed and not parsed.active:
        console.print(
            Panel(
                f"[dim]{parsed.summary}[/dim]\n[bold]Not an investment[/bold]",
                title="Result",
                border_style="yellow",
            )
        )
    else:
        console.print(Panel("[red]No valid parse result[/red]", border_style="red"))


def _process_row_interactive(
    row: dict[str, str],
    row_index: int,
    provider: LLMProvider,
    model: str,
    existing_symbols: list[str],
    temperature: float,
) -> LlmAssetResponse | None:
    """Process a single row interactively: stream, display, prompt user."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt

    console = Console()

    prompt = _build_prompt(row, existing_symbols)

    while True:
        # Stream the response
        console.print()
        console.rule(f"[bold]Row {row_index}[/bold]")
        console.print(
            Panel(
                _format_row_brief(row),
                title="Input Row",
                border_style="dim",
            )
        )

        console.print("[dim]Querying LLM...[/dim]")

        collected = ""
        try:
            for chunk in provider.stream_completion(prompt, model=model, temperature=temperature):
                collected += chunk
                console.print(chunk, end="", highlight=False)
        except Exception as exc:
            console.print(f"\n[red]LLM error: {exc}[/red]")
            return None

        console.print()

        # Parse the collected response
        try:
            parsed = LlmAssetResponse.model_validate_json(collected)
        except Exception:
            try:
                match = re.search(r"\{.*\}", collected, re.DOTALL)
                if match:
                    parsed = LlmAssetResponse.model_validate_json(match.group())
                else:
                    console.print("[red]Failed to parse LLM response.[/red]")
                    parsed = None
            except Exception:
                console.print("[red]Failed to parse LLM response.[/red]")
                parsed = None

        # Edit loop: display table, prompt for field=value edits, repeat
        while True:
            _display_parsed_table(console, parsed)

            console.print(
                "[dim]field=value to edit · Enter to accept · r re-run · s skip · q quit[/dim]"
            )
            raw = Prompt.ask("[bold]>[/bold]", default="", show_default=False)
            raw = raw.strip()

            if not raw:
                return parsed

            if raw == "r":
                break  # re-run LLM (outer while loop)

            if raw == "s":
                return None

            if raw == "q":
                raise click.Abort()

            # field=value edit
            if "=" not in raw:
                console.print("[yellow]Use: field=value (e.g. symbol=AAPL)[/yellow]")
                continue

            key, _, value = raw.partition("=")
            key = key.strip()
            if key not in _EDITABLE_FIELDS:
                console.print(
                    f"[yellow]Unknown field: {key}. Valid: {', '.join(sorted(_EDITABLE_FIELDS))}[/yellow]"
                )
                continue

            if parsed is None or not parsed.active or not parsed.investment:
                console.print("[yellow]No parsed investment to edit.[/yellow]")
                continue

            new_val = None if value.strip().lower() == "null" else value.strip()
            setattr(parsed.investment, key, new_val)

    return None  # unreachable


def _format_row_brief(row: dict[str, str]) -> str:
    """One-line summary of a CSV row for display."""
    parts = []
    for k, v in row.items():
        if v and v.strip():
            parts.append(f"{k}: {v}")
    return " | ".join(parts[:8])  # First 8 non-empty fields


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command("assets")
@click.option(
    "--input",
    "input_csv",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Input CSV file.",
)
@click.option(
    "--db", "db_path", default="omnifin.db", show_default=True, help="SQLite database path."
)
@click.option("--model", default="gemma4:31b", show_default=True, help="LLM model name.")
@click.option(
    "--provider",
    "provider_url",
    default="ollama",
    show_default=True,
    help="LLM provider: 'gemini' or an Ollama/OpenAI-compatible URL.",
)
@click.option(
    "--partial",
    "partial_csv",
    default=None,
    type=click.Path(exists=True, dir_okay=False),
    help="Partial results CSV for warm start (skip already-processed rows).",
)
@click.option(
    "--progress",
    "progress_csv",
    default=None,
    type=click.Path(dir_okay=False),
    help="Save results to CSV instead of database.",
)
@click.option(
    "--parse",
    "parsed_only",
    is_flag=True,
    default=False,
    help="In progress output, emit only parsed fields (no original columns).",
)
@click.option(
    "--yes", "-y", is_flag=True, default=False, help="Skip confirmation when writing to database."
)
@click.option(
    "--interactive",
    "-i",
    "interactive",
    is_flag=True,
    default=False,
    help="Stream AI responses and review/edit each row interactively.",
)
@click.option(
    "--temperature", type=float, default=0.0, show_default=True, help="LLM sampling temperature."
)
@click.option(
    "--no-auto-parse",
    "auto_parse_enabled",
    is_flag=True,
    flag_value=False,
    default=True,
    help="Disable auto-parse (skip rows matching same column/value without LLM calls).",
)
def assets_command(
    input_csv: str,
    db_path: str,
    model: str,
    provider_url: str,
    partial_csv: str | None,
    progress_csv: str | None,
    parsed_only: bool,
    yes: bool,
    interactive: bool,
    temperature: float,
    auto_parse_enabled: bool,
) -> None:
    """Detect investments in a transaction CSV using LLM and add them to the database."""
    console = Console()

    # 1. Load input CSV
    headers, rows = _load_csv(Path(input_csv))
    console.print(f"[bold]Loaded {len(rows)} rows from {input_csv}[/bold]")

    # 2. Load partial results for warm start
    partial_map: dict[str, LlmAssetResponse] = {}
    if partial_csv:
        partial_map = _load_partial(Path(partial_csv))
        console.print(f"[dim]Loaded {len(partial_map)} partial results from {partial_csv}[/dim]")

    # 3. Build row results, pre-filling from partial
    existing_symbols = _load_existing_symbols(db_path)
    results: list[RowResult] = []
    to_process: list[int] = []  # indices into results that need LLM processing

    for idx, row in enumerate(rows, start=1):
        h = _row_hash(row)
        result = RowResult(index=idx, source_row=row, row_hash=h)
        if h in partial_map:
            result.parsed = partial_map[h]
            result.from_partial = True
        else:
            to_process.append(len(results))
        results.append(result)

    skipped = len(results) - len(to_process)
    if skipped:
        console.print(
            f"[dim]{skipped} rows loaded from partial, {len(to_process)} to process[/dim]"
        )

    # 4. Set up progress writer (opens file, writes header, flushes partial rows)
    progress_writer: ProgressWriter | None = None
    if progress_csv:
        progress_writer = ProgressWriter(Path(progress_csv), headers, parsed_only)
        for r in results:
            if r.from_partial:
                progress_writer.write_row(r)

    # 5. Apply auto-parse from partial results (skips remaining rows with same column/value)
    auto_filled_total = 0
    if auto_parse_enabled:
        for r in results:
            if r.from_partial and r.parsed and r.parsed.auto_parse:
                n = _auto_fill_rows(results, r.parsed, headers, progress_writer)
                if n:
                    col = r.parsed.auto_parse.column
                    val = r.parsed.auto_parse.value
                    console.print(
                        f"[cyan]Auto-filled {n} rows matching {col}={val} (from partial)[/cyan]"
                    )
                    auto_filled_total += n
        if auto_filled_total:
            to_process = [i for i in to_process if results[i].parsed is None]
            console.print(
                f"[bold cyan]Auto-filled {auto_filled_total} rows from partial results (skipped LLM calls)[/bold cyan]"
            )

    if not to_process:
        console.print("[bold green]All rows already processed (from partial).[/bold green]")
    else:
        # 5. Create provider
        provider = LLMProvider.from_url(provider_url, model=model)
        console.print(
            f"[dim]Provider: {provider_url} | Model: {model} | Temperature: {temperature}[/dim]"
        )

        # 6. Process rows
        if interactive:
            auto_filled_total += _run_interactive(
                console,
                results,
                to_process,
                provider,
                model,
                existing_symbols,
                temperature,
                progress_writer=progress_writer,
                auto_parse_enabled=auto_parse_enabled,
            )
        else:
            batch_auto_filled, _ = _run_batch(
                console,
                results,
                to_process,
                provider,
                model,
                existing_symbols,
                temperature,
                progress_writer=progress_writer,
                auto_parse_enabled=auto_parse_enabled,
            )
            auto_filled_total += batch_auto_filled

    # 7. Finalize
    if auto_filled_total:
        console.print(
            f"[bold cyan]Auto-filled {auto_filled_total} rows total (skipped LLM calls)[/bold cyan]"
        )

    if progress_writer:
        progress_writer.close()
        console.print(f"[bold green]Wrote progress to {progress_csv}[/bold green]")
    elif not to_process:
        pass  # nothing to do — all from partial, no progress flag
    else:
        _report_and_save(console, results, db_path, input_csv, yes)


def _run_interactive(
    console: Console,
    results: list[RowResult],
    to_process: list[int],
    provider: LLMProvider,
    model: str,
    existing_symbols: list[str],
    temperature: float,
    progress_writer: ProgressWriter | None = None,
    auto_parse_enabled: bool = True,
) -> int:
    """Process rows one by one with streaming and user review.

    Returns ``auto_filled_total``.
    """
    auto_filled_total = 0
    remaining = list(to_process)

    while remaining:
        idx = remaining.pop(0)
        r = results[idx]
        console.print(f"\n[dim]Processing row {r.index} ({len(remaining)} remaining)[/dim]")

        parsed = _process_row_interactive(
            r.source_row,
            r.index,
            provider,
            model,
            existing_symbols,
            temperature,
        )
        r.parsed = parsed
        if parsed and parsed.active and parsed.investment:
            sym = parsed.investment.symbol or "?"
            if sym not in existing_symbols:
                existing_symbols.append(sym)

        if progress_writer:
            progress_writer.write_row(r)

        # Auto-fill remaining rows matching auto_parse column/value
        if auto_parse_enabled and r.parsed and r.parsed.auto_parse:
            n = _auto_fill_rows(results, r.parsed, headers=None, progress_writer=progress_writer)
            if n:
                col = r.parsed.auto_parse.column
                val = r.parsed.auto_parse.value
                # Collect auto-filled rows before filtering remaining
                auto_filled_indices = [j for j in remaining if results[j].parsed is not None]
                # Show table of auto-filled rows
                from rich.table import Table as _Table

                auto_table = _Table(
                    title=f"Auto-filled {n} rows matching {col}={val}",
                    border_style="cyan",
                )
                auto_table.add_column("Row #", style="bold")
                auto_table.add_column("Symbol")
                auto_table.add_column("Name")
                auto_table.add_column("Summary")
                for j in auto_filled_indices:
                    inv = (
                        results[j].parsed.investment
                        if results[j].parsed and results[j].parsed.investment
                        else None
                    )
                    auto_table.add_row(
                        str(results[j].index),
                        inv.symbol if inv else "-",
                        inv.name if inv else "-",
                        results[j].parsed.summary if results[j].parsed else "-",
                    )
                console.print(auto_table)
                auto_filled_total += n
                remaining = [j for j in remaining if results[j].parsed is None]

    return auto_filled_total


def _run_batch(
    console: Console,
    results: list[RowResult],
    to_process: list[int],
    provider: LLMProvider,
    model: str,
    existing_symbols: list[str],
    temperature: float,
    progress_writer: ProgressWriter | None = None,
    auto_parse_enabled: bool = True,
) -> tuple[int, int]:
    """Process rows in batch with a progress bar.

    Returns ``(auto_filled_total, error_count)``.
    """
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    auto_filled_total = 0
    error_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing rows...", total=len(to_process))

        i = 0
        while i < len(to_process):
            idx = to_process[i]
            r = results[idx]
            progress.update(task, description=f"Row {r.index}/{len(results)}")

            prompt = _build_prompt(r.source_row, existing_symbols)

            try:
                parsed = provider.structured_completion(
                    prompt,
                    LlmAssetResponse,
                    model=model,
                    temperature=temperature,
                )
                r.parsed = parsed
                if parsed and parsed.active and parsed.investment:
                    sym = parsed.investment.symbol or "?"
                    if sym not in existing_symbols:
                        existing_symbols.append(sym)
            except Exception as exc:
                console.print(f"\n[yellow]Row {r.index}: LLM error: {exc}[/yellow]")
                r.parsed = LlmAssetResponse(
                    summary=f"Error: {exc}",
                    confidence=0.0,
                    active=False,
                )
                error_count += 1

            if progress_writer:
                progress_writer.write_row(r)

            # Auto-fill remaining rows matching auto_parse column/value
            if auto_parse_enabled and r.parsed and r.parsed.auto_parse:
                n = _auto_fill_rows(
                    results, r.parsed, headers=None, progress_writer=progress_writer
                )
                if n:
                    col = r.parsed.auto_parse.column
                    val = r.parsed.auto_parse.value
                    console.print(f"\n  [cyan]Auto-filled {n} rows matching {col}={val}[/cyan]")
                    auto_filled_total += n
                    # Remove auto-filled indices from to_process (they are now after i)
                    to_process[:] = to_process[: i + 1] + [
                        j for j in to_process[i + 1 :] if results[j].parsed is None
                    ]
                    progress.update(task, total=len(to_process))

            progress.advance(task)
            i += 1

    return auto_filled_total, error_count


def _report_and_save(
    console: Console,
    results: list[RowResult],
    db_path: str,
    input_csv: str,
    yes: bool,
) -> None:
    """Print summary and optionally save to database."""
    from rich.table import Table

    new_count = 0
    known_count = 0
    non_invest_count = 0
    error_count = 0

    for r in results:
        if r.parsed is None:
            error_count += 1
        elif r.parsed.active:
            if r.parsed.investment and r.parsed.investment.symbol:
                new_count += 1
            else:
                known_count += 1
        else:
            non_invest_count += 1

    table = Table(title="Parse Summary", show_header=False)
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Total rows", str(len(results)))
    table.add_row("Investments found", str(new_count), style="green")
    table.add_row("Known/other", str(known_count))
    table.add_row("Non-investment rows", str(non_invest_count), style="dim")
    if error_count:
        table.add_row("Errors", str(error_count), style="red")
    console.print(table)

    if not new_count:
        console.print("[dim]No new investments to save.[/dim]")
        return

    if not yes:
        from rich.prompt import Confirm

        if not Confirm.ask(f"Save {new_count} new investment(s) to {db_path}?"):
            console.print("[dim]Skipped database write.[/dim]")
            return

    # Save to database
    filename = Path(input_csv).name
    doc_hash = stable_hash_bytes(Path(input_csv).read_bytes())

    with DatabaseSession(db_path) as session:
        report = Report(
            _session=session,
            name=f"Assets: {filename}",
            raw_hash=doc_hash,
        )

        investments_by_symbol: dict[str, Investment] = {}
        for asset in session.all(Asset, limit=10000):
            if asset.symbol:
                investments_by_symbol[asset.symbol.upper()] = Investment(
                    _session=session, symbol=asset.symbol.upper()
                )

        objects: list[Any] = []
        for r in results:
            if r.parsed:
                objects.extend(
                    _build_investment_objects(
                        session=session,
                        parsed=r.parsed,
                        investments_by_symbol=investments_by_symbol,
                    )
                )

        if not objects:
            console.print("[dim]No new investment objects to write.[/dim]")
            return

        plan = report.plan(*objects)
        if not plan.is_valid:
            console.print("[red]Plan validation failed:[/red]")
            for err in plan.errors:
                console.print(f"  - {err}")
            return

        report.save(*objects)
        console.print(
            f"[bold green]Saved {len(objects)} investment(s) via report {report.id}[/bold green]"
        )
