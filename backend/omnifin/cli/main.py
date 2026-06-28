"""Command line interface for the installable ``fin`` command."""

from __future__ import annotations

import json
from pathlib import Path

import click
import uvicorn

from omnifin.core.db import DatabaseSession, init_db
from omnifin.ingest.normalize import normalize_csv_file, write_normalized_csv
from omnifin.models import Report


@click.group()
def cli() -> None:
    """Omnifin command line tools."""


@cli.command("init-db")
@click.option("--db", "db_path", default="omnifin.db", show_default=True, help="SQLite database path.")
def init_db_command(db_path: str) -> None:
    """Create or migrate the SQLite schema."""

    with DatabaseSession(db_path, initialize=False) as session:
        init_db(session.conn)  # type: ignore[arg-type]
    click.echo(f"Initialized {db_path}")


@cli.command("normalize")
@click.argument("input_csv", type=click.Path(exists=True, dir_okay=False))
@click.option("--db", "db_path", default="omnifin.db", show_default=True, help="SQLite database path.")
@click.option("--output", "output_csv", type=click.Path(dir_okay=False), help="Optional normalized CSV output path.")
@click.option("--account-name", default="Imported Account", show_default=True)
@click.option("--account-type", default="internal", show_default=True)
@click.option("--source-name", default=None, help="Human-readable source/report name.")
@click.option("--save/--no-save", default=False, show_default=True, help="Persist parsed objects to SQLite.")
@click.option("--json-plan/--no-json-plan", default=False, show_default=True, help="Print plan as JSON.")
def normalize_command(
    input_csv: str,
    db_path: str,
    output_csv: str | None,
    account_name: str,
    account_type: str,
    source_name: str | None,
    save: bool,
    json_plan: bool,
) -> None:
    """Normalize an arbitrary CSV using the universal transfer foundation."""

    result = normalize_csv_file(
        input_csv,
        source_name=source_name,
        account_name=account_name,
        account_type=account_type,
    )
    if output_csv:
        write_normalized_csv(result.rows, output_csv)
        click.echo(f"Wrote normalized CSV to {output_csv}")
    else:
        for row in result.rows:
            click.echo(row.model_dump_json())

    with DatabaseSession(db_path) as session:
        report = Report(_session=session, id=result.report.id, date=result.report.date, name=result.report.name, raw_hash=result.report.raw_hash)
        plan = report.plan(*result.objects)
        if json_plan:
            click.echo(plan.model_dump_json(indent=2))
        else:
            click.echo(f"Plan valid: {plan.is_valid}")
            click.echo(f"Inserts: {plan.inserts}")
            click.echo(f"Updates: {plan.updates}")
            if plan.errors:
                click.echo("Errors:")
                for error in plan.errors:
                    click.echo(f"  - {error}")
        if save:
            report.save(*result.objects)
            click.echo(f"Saved report {report.id}")


@cli.command("tax")
@click.option("--db", "db_path", default="omnifin.db", show_default=True, help="SQLite database path.")
@click.option("--jurisdiction", type=click.Choice(["US", "DE"]), required=True)
@click.option("--year", "tax_year", type=int, required=True)
def tax_command(db_path: str, jurisdiction: str, tax_year: int) -> None:
    """Run the scaffold tax calculator for a jurisdiction/year."""

    from omnifin.models import Transfer
    from omnifin.tax.de import calculate_german_tax
    from omnifin.tax.us import calculate_us_tax

    with DatabaseSession(db_path) as session:
        transfers = session.all(Transfer, limit=100000)
        if jurisdiction == "US":
            result = calculate_us_tax(transfers, tax_year=tax_year)
        else:
            result = calculate_german_tax(transfers, tax_year=tax_year)
    click.echo(result.model_dump_json(indent=2))


@cli.command("serve")
@click.option("--db", "db_path", default="omnifin.db", show_default=True, help="SQLite database path.")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True)
@click.option("--reload/--no-reload", default=True, show_default=True)
def serve_command(db_path: str, host: str, port: int, reload: bool) -> None:
    """Start the FastAPI backend server."""

    # Environment variable keeps uvicorn reload mode simple.
    import os

    os.environ["OMNIFIN_DB"] = db_path
    uvicorn.run("omnifin.api.server:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    cli()
