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

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_TEMPLATE_PATH = REPO_ROOT / "assets" / "asset_parse_prompt.md"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ParsedAsset(BaseModel):
    """Investment metadata extracted by the LLM for a single row."""

    active: bool = False
    symbol: str | None = None
    name: str | None = None
    category: str | None = None
    nyse_ticker: str | None = None
    ibkr_ticker: str | None = None
    identifier: str | None = None
    identifier_type: str | None = None
    country: str | None = None
    fund_type: str | None = None
    fund_focus: str | None = None
    confidence: float = 0.0
    summary: str = ""


class LlmAssetResponse(BaseModel):
    """Full LLM response schema for structured investment parsing."""

    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    active: bool = False
    investment: ParsedAsset | None = None


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
                    category=row.get("category") or None,
                    nyse_ticker=row.get("nyse_ticker") or None,
                    ibkr_ticker=row.get("ibkr_ticker") or None,
                    identifier=row.get("identifier") or None,
                    identifier_type=row.get("identifier_type") or None,
                    country=row.get("country") or None,
                    fund_type=row.get("fund_type") or None,
                    fund_focus=row.get("fund_focus") or None,
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
# Prompt building
# ---------------------------------------------------------------------------


def _build_prompt(row: dict[str, str], existing_symbols: list[str]) -> str:
    if PROMPT_TEMPLATE_PATH.exists():
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = _fallback_prompt()

    replacements = {
        "row_json": json.dumps(row, ensure_ascii=False, indent=2),
        "existing_symbols_json": json.dumps(existing_symbols, ensure_ascii=False),
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


def _write_progress_csv(
    path: Path,
    headers: list[str],
    results: list[RowResult],
    *,
    parsed_only: bool = False,
) -> None:
    """Write the progress CSV: original columns (optional) + parsed fields + row_hash."""
    out_fields = list(headers) if not parsed_only else []
    out_fields.extend(["row_hash"] + _PARSED_FIELDS)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            row: dict[str, Any] = {}
            if not parsed_only:
                for h in headers:
                    row[h] = r.source_row.get(h, "")
            row["row_hash"] = r.row_hash
            if r.parsed:
                row["active"] = str(r.parsed.active)
                if r.parsed.investment:
                    inv = r.parsed.investment
                    row["symbol"] = inv.symbol or ""
                    row["name"] = inv.name or ""
                    row["category"] = inv.category or ""
                    row["nyse_ticker"] = inv.nyse_ticker or ""
                    row["ibkr_ticker"] = inv.ibkr_ticker or ""
                    row["identifier"] = inv.identifier or ""
                    row["identifier_type"] = inv.identifier_type or ""
                    row["country"] = inv.country or ""
                    row["fund_type"] = inv.fund_type or ""
                    row["fund_focus"] = inv.fund_focus or ""
                    row["confidence"] = str(inv.confidence)
                    row["summary"] = r.parsed.summary
                else:
                    row["confidence"] = str(r.parsed.confidence)
                    row["summary"] = r.parsed.summary
            else:
                row["active"] = "false"
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Interactive mode (rich TUI)
# ---------------------------------------------------------------------------


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
    from rich.table import Table

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

        console.print("[dim]Querying LLM...[/dim]", end="")

        collected = ""
        try:
            for chunk in provider.stream_completion(prompt, model=model, temperature=temperature):
                collected += chunk
                # Update the spinner-like indicator
                console.print(".", end="", highlight=False)
        except Exception as exc:
            console.print(f"\n[red]LLM error: {exc}[/red]")
            return None

        console.print(" [green]done[/green]")

        # Parse the collected response
        try:
            parsed = LlmAssetResponse.model_validate_json(collected)
        except Exception:
            try:
                # Try to extract JSON from the response
                match = re.search(r"\{.*\}", collected, re.DOTALL)
                if match:
                    parsed = LlmAssetResponse.model_validate_json(match.group())
                else:
                    console.print("[red]Failed to parse LLM response.[/red]")
                    parsed = None
            except Exception:
                console.print("[red]Failed to parse LLM response.[/red]")
                parsed = None

        # Display the result
        if parsed and parsed.active and parsed.investment:
            inv = parsed.investment
            table = Table(title="Parsed Investment", show_header=False, border_style="green")
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

        # Prompt user for action
        choice = Prompt.ask(
            "[bold]Action[/bold]",
            choices=["a", "e", "r", "s", "q"],
            default="a",
            show_choices=False,
            show_default=True,
        )

        if choice == "a":
            return parsed
        elif choice == "e":
            parsed = _edit_parsed(console, parsed)
            if parsed:
                return parsed
        elif choice == "r":
            continue  # Re-run the LLM call
        elif choice == "s":
            return None
        elif choice == "q":
            raise click.Abort()

    return None  # unreachable


def _format_row_brief(row: dict[str, str]) -> str:
    """One-line summary of a CSV row for display."""
    parts = []
    for k, v in row.items():
        if v and v.strip():
            parts.append(f"{k}: {v}")
    return " | ".join(parts[:8])  # First 8 non-empty fields


def _edit_parsed(console: Console, parsed: LlmAssetResponse) -> LlmAssetResponse | None:
    """Let the user edit individual fields of the parsed result."""
    from rich.prompt import Prompt

    inv = parsed.investment
    if inv is None:
        return parsed

    fields = [
        ("symbol", inv.symbol or ""),
        ("name", inv.name or ""),
        ("category", inv.category or ""),
        ("country", inv.country or ""),
        ("fund_type", inv.fund_type or ""),
        ("fund_focus", inv.fund_focus or ""),
        ("identifier", inv.identifier or ""),
        ("identifier_type", inv.identifier_type or ""),
        ("nyse_ticker", inv.nyse_ticker or ""),
        ("ibkr_ticker", inv.ibkr_ticker or ""),
    ]

    console.print("[dim]Press Enter to keep current value, type 'null' to clear.[/dim]")

    for field_name, current in fields:
        new_val = Prompt.ask(f"  {field_name}", default=current)
        if new_val == "null":
            new_val = None
        setattr(inv, field_name, new_val)

    # Rebuild the investment with potentially changed fields
    parsed.investment = inv
    return parsed


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

    if not to_process:
        console.print("[bold green]All rows already processed (from partial).[/bold green]")
    else:
        # 4. Create provider
        provider = LLMProvider.from_url(provider_url, model=model)
        console.print(
            f"[dim]Provider: {provider_url} | Model: {model} | Temperature: {temperature}[/dim]"
        )

        # 5. Process rows
        if interactive:
            _run_interactive(
                console, results, to_process, provider, model, existing_symbols, temperature
            )
        else:
            _run_batch(console, results, to_process, provider, model, existing_symbols, temperature)

    # 6. Output results
    if progress_csv:
        _write_progress_csv(Path(progress_csv), headers, results, parsed_only=parsed_only)
        console.print(f"[bold green]Wrote progress to {progress_csv}[/bold green]")
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
) -> None:
    """Process rows one by one with streaming and user review."""
    total = len(to_process)
    for i, idx in enumerate(to_process, start=1):
        r = results[idx]
        console.print(f"\n[dim]Processing {i}/{total} (row {r.index})[/dim]")

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


def _run_batch(
    console: Console,
    results: list[RowResult],
    to_process: list[int],
    provider: LLMProvider,
    model: str,
    existing_symbols: list[str],
    temperature: float,
) -> None:
    """Process rows in batch with a progress bar."""
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Processing rows...", total=len(to_process))

        for idx in to_process:
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

            progress.advance(task)


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
