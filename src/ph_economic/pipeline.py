"""
Pipeline CLI entry point.

Commands:
  ph-tracker ingest     — fetch from PSA + World Bank + BSP → PostgreSQL
  ph-tracker transform  — run dbt models
  ph-tracker status     — print warehouse row counts + latest data dates
  ph-tracker reset      — drop and recreate raw schema (destructive)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from ph_economic.config import settings
from ph_economic.ingestion.bsp import BSPClient
from ph_economic.ingestion.psa import PSAClient
from ph_economic.ingestion.worldbank import WorldBankClient
from ph_economic.loader import WarehouseLoader

app = typer.Typer(
    name="ph-tracker",
    help="Philippine Economic Indicators + OFW Remittance Pipeline",
    no_args_is_help=True,
)
console = Console()


def _run_dbt(target: str = "prod") -> None:
    console.print(f"\n[bold cyan]→[/] Running dbt transforms (target: {target})...")
    result = subprocess.run(
        [
            "dbt", "run",
            "--profiles-dir", settings.dbt_profiles_dir,
            "--project-dir", settings.dbt_project_dir,
            "--target", target,
        ],
    )
    if result.returncode != 0:
        console.print("[bold red]dbt run failed — see output above.[/]")
        raise typer.Exit(code=1)
    console.print("[bold green]✓[/] dbt transforms complete")


def _run_dbt_test(target: str = "prod") -> None:
    result = subprocess.run(
        [
            "dbt", "test",
            "--profiles-dir", settings.dbt_profiles_dir,
            "--project-dir", settings.dbt_project_dir,
            "--target", target,
        ],
    )
    if result.returncode != 0:
        console.print("[bold yellow]dbt test warnings — see output above.[/]")
    else:
        console.print("[bold green]✓[/] dbt tests passed")


@app.command()
def ingest(
    source: list[str] | None = typer.Option(
        None, "--source", "-s",
        help="Sources to ingest: psa, worldbank, bsp. Defaults to all.",
    ),
    bsp_csv: str | None = typer.Option(
        None, "--bsp-csv",
        help="Path to BSP monthly remittance CSV file.",
    ),
    skip_dbt: bool = typer.Option(False, "--skip-dbt", help="Skip dbt after ingest."),
) -> None:
    """Fetch data from all sources and load into PostgreSQL."""
    sources = set(source) if source else {"psa", "worldbank", "bsp"}
    console.rule("[bold]Philippine Economic Tracker — Ingest[/]")

    all_indicators = []
    all_remittances = []

    # PSA — CPI monthly
    if "psa" in sources:
        console.print("\n[bold]PSA OpenSTAT[/]")
        with PSAClient() as psa:
            all_indicators.extend(psa.fetch_all())

    # World Bank — GDP, CPI annual + remittances
    if "worldbank" in sources:
        console.print("\n[bold]World Bank API[/]")
        with WorldBankClient() as wb:
            all_indicators.extend(wb.fetch_all_indicators())
            all_remittances.extend(wb.fetch_remittances())

    # BSP — monthly remittances (optional CSV)
    if "bsp" in sources:
        console.print("\n[bold]BSP[/]")
        with BSPClient(csv_path=bsp_csv) as bsp:
            all_remittances.extend(bsp.fetch_monthly_remittances())

    # Load into PostgreSQL
    console.print("\n[bold]Loading to PostgreSQL[/]")
    with WarehouseLoader() as loader:
        loader.upsert_indicators(all_indicators)
        loader.upsert_remittances(all_remittances)
        ind_total = loader.indicator_count()
        rem_total = loader.remittance_count()
        console.print(f"  Total indicator rows : [bold]{ind_total}[/]")
        console.print(f"  Total remittance rows: [bold]{rem_total}[/]")

    if not skip_dbt:
        _run_dbt()
        _run_dbt_test()

    console.rule("[bold green]Ingest complete[/]")


@app.command()
def transform(
    target: str = typer.Option("prod", "--target", "-t", help="dbt target profile."),
) -> None:
    """Run dbt transforms only (warehouse must already have data)."""
    _run_dbt(target=target)
    _run_dbt_test(target=target)


@app.command()
def status() -> None:
    """Print current warehouse statistics and latest data dates."""
    with WarehouseLoader() as loader:
        ind_count = loader.indicator_count()
        rem_count = loader.remittance_count()

        latest_df = loader.fetch_dataframe("""
            SELECT series_code, series_name,
                   MAX(period_date) AS latest_period,
                   COUNT(*)        AS row_count
            FROM raw.economic_indicators
            GROUP BY series_code, series_name
            ORDER BY series_code
        """)
        rem_df = loader.fetch_dataframe("""
            SELECT source, frequency,
                   MAX(period_date) AS latest_period,
                   COUNT(*)        AS row_count
            FROM raw.ofw_remittances
            GROUP BY source, frequency
            ORDER BY source
        """)

    summary = Table(title="Warehouse Status", show_header=True)
    summary.add_column("Metric", style="bold")
    summary.add_column("Value", justify="right")
    summary.add_row("Economic indicator rows", str(ind_count))
    summary.add_row("Remittance rows", str(rem_count))
    console.print(summary)

    if len(latest_df) > 0:
        ind_table = Table(title="Indicators — Latest Dates", show_header=True)
        ind_table.add_column("Series Code")
        ind_table.add_column("Series Name")
        ind_table.add_column("Latest Period", justify="right")
        ind_table.add_column("Rows", justify="right")
        for row in latest_df.iter_rows(named=True):
            ind_table.add_row(
                str(row["series_code"]),
                str(row["series_name"])[:40],
                str(row["latest_period"]),
                str(row["row_count"]),
            )
        console.print(ind_table)

    if len(rem_df) > 0:
        rem_table = Table(title="Remittances — Latest Dates", show_header=True)
        rem_table.add_column("Source")
        rem_table.add_column("Frequency")
        rem_table.add_column("Latest Period", justify="right")
        rem_table.add_column("Rows", justify="right")
        for row in rem_df.iter_rows(named=True):
            rem_table.add_row(*[str(v) for v in row.values()])
        console.print(rem_table)


@app.command()
def reset(
    confirm: bool = typer.Option(
        False, "--confirm", "-y", help="Confirm destructive reset.",
    ),
) -> None:
    """Drop and recreate raw schema. DESTRUCTIVE — all data is lost."""
    if not confirm:
        console.print("[bold red]Add --confirm / -y to proceed. This deletes all data.[/]")
        raise typer.Exit(code=1)

    import psycopg2
    console.print("[bold red]Resetting raw schema...[/]")
    conn = psycopg2.connect(settings.postgres_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("DROP SCHEMA IF EXISTS raw CASCADE;")
    finally:
        conn.close()
    console.print("[bold green]✓[/] Raw schema dropped. Run `ph-tracker ingest` to reload.")


if __name__ == "__main__":
    app()
