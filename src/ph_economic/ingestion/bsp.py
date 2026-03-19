"""
BSP (Bangko Sentral ng Pilipinas) data client.

BSP does not expose a public REST API. Monthly OFW remittance data is
published as Excel/CSV on the BSP website but requires form-based download.

Strategy:
  - For annual totals: delegate to WorldBankClient (authoritative, reliable)
  - For monthly granularity: parse BSP published CSV when path is provided
  - If neither is available: log warning and return empty list (pipeline continues)

This design means the pipeline never breaks on missing BSP data —
the World Bank annual series always provides a complete baseline.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from rich.console import Console

from ph_economic.config import settings
from ph_economic.models import DataSource, Frequency, OFWRemittance

console = Console()

# Expected columns in BSP monthly remittance CSV
# Format: Year, Month, Total (USD Millions), Land-based, Sea-based
_BSP_YEAR_COL = 0
_BSP_MONTH_COL = 1
_BSP_TOTAL_COL = 2

_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_bsp_month(year_str: str, month_str: str) -> date | None:
    """Parse BSP year and month strings into a date."""
    try:
        year = int(str(year_str).strip())
        month_lower = str(month_str).strip().lower()
        if month_lower.isdigit():
            month = int(month_lower)
        else:
            month = _MONTH_MAP.get(month_lower)
            if not month:
                return None
        return date(year, month, 1)
    except (ValueError, TypeError):
        return None


def _parse_bsp_value(raw: str) -> Decimal | None:
    """Parse a BSP value cell — handles commas, dashes, blanks."""
    cleaned = str(raw).strip().replace(",", "").replace(" ", "")
    if not cleaned or cleaned in ("-", "..", "N/A", "n/a"):
        return None
    try:
        # BSP reports in USD millions
        return Decimal(cleaned) * Decimal("1_000_000")
    except Exception:
        return None


class BSPClient:
    """
    BSP remittance data client.

    Primary mode: parse BSP monthly CSV if path is provided via
    BSP_CSV_PATH env var or the csv_path constructor argument.

    Fallback: returns empty list — pipeline uses World Bank annual data instead.

    The monthly detail is a nice-to-have enrichment. Never a hard dependency.

    Usage:
        with BSPClient(csv_path="data/bsp_remittances.csv") as client:
            records = client.fetch_monthly_remittances()
    """

    def __init__(self, csv_path: str | Path | None = None) -> None:
        self._csv_path = Path(csv_path) if csv_path else None

    def __enter__(self) -> "BSPClient":
        return self

    def __exit__(self, *_: Any) -> None:
        pass

    def fetch_monthly_remittances(self) -> list[OFWRemittance]:
        """
        Parse BSP monthly CSV into OFWRemittance records.
        Returns empty list if no CSV path is configured.
        """
        if not self._csv_path:
            console.print(
                "  [dim]BSP: no CSV path configured — "
                "using World Bank annual data only[/]"
            )
            return []

        if not self._csv_path.exists():
            console.print(
                f"  [yellow]⚠ BSP: CSV not found at {self._csv_path}[/]"
            )
            return []

        console.print(f"  [cyan]→[/] BSP parsing {self._csv_path}...")
        records: list[OFWRemittance] = []

        try:
            content = self._csv_path.read_text(encoding="utf-8-sig")
            reader = csv.reader(io.StringIO(content))

            # Skip header rows — BSP CSVs typically have 2–4 header lines
            rows = list(reader)
            data_start = 0
            for i, row in enumerate(rows):
                if row and str(row[0]).strip().isdigit():
                    data_start = i
                    break

            for row in rows[data_start:]:
                if len(row) < 3:
                    continue
                period = _parse_bsp_month(row[_BSP_YEAR_COL], row[_BSP_MONTH_COL])
                if not period:
                    continue
                if period.year < settings.start_year:
                    continue

                value_usd = _parse_bsp_value(row[_BSP_TOTAL_COL])
                if value_usd is None:
                    continue

                try:
                    record = OFWRemittance(
                        source=DataSource.BSP,
                        period_date=period,
                        frequency=Frequency.MONTHLY,
                        remittance_usd=value_usd,
                        country_destination="ALL",
                        notes="BSP monthly remittances (land-based + sea-based)",
                    )
                    records.append(record)
                except Exception as exc:
                    console.print(f"  [dim]BSP skip {period}: {exc}[/]")

        except Exception as exc:
            console.print(f"  [red]BSP parse error: {exc}[/]")

        console.print(f"    [green]✓[/] {len(records)} BSP monthly records")
        return records
