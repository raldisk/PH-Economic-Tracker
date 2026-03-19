"""
PostgreSQL warehouse loader.

Schema:
  raw.economic_indicators   — PSA + World Bank time-series
  raw.ofw_remittances       — OFW remittance records (World Bank + BSP)

Upsert keys:
  economic_indicators : (source, series_code, period_date)
  ofw_remittances     : (source, period_date, country_destination)

All inserts are idempotent — re-running on the same data is safe.
"""

from __future__ import annotations

from typing import Any

import polars as pl
import psycopg2
import psycopg2.extras
from rich.console import Console

from ph_economic.config import settings
from ph_economic.models import EconomicIndicator, OFWRemittance

console = Console()

# ── DDL ───────────────────────────────────────────────────────────────────────

_DDL_SCHEMA = "CREATE SCHEMA IF NOT EXISTS raw;"

_DDL_ECONOMIC_INDICATORS = """
CREATE TABLE IF NOT EXISTS raw.economic_indicators (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT            NOT NULL,
    series_code     TEXT            NOT NULL,
    series_name     TEXT            NOT NULL,
    period_date     DATE            NOT NULL,
    frequency       TEXT            NOT NULL,
    value           NUMERIC(20, 6),
    unit            TEXT            NOT NULL DEFAULT '',
    country_code    CHAR(3)         NOT NULL DEFAULT 'PH',
    notes           TEXT,
    loaded_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (source, series_code, period_date)
);
"""

_DDL_OFW_REMITTANCES = """
CREATE TABLE IF NOT EXISTS raw.ofw_remittances (
    id                  BIGSERIAL PRIMARY KEY,
    source              TEXT            NOT NULL,
    period_date         DATE            NOT NULL,
    frequency           TEXT            NOT NULL,
    remittance_usd      NUMERIC(20, 2),
    remittance_pct_gdp  NUMERIC(10, 4),
    country_destination TEXT            NOT NULL DEFAULT 'ALL',
    ofw_count           INTEGER,
    notes               TEXT,
    loaded_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    UNIQUE (source, period_date, country_destination)
);
"""

_DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_ei_series ON raw.economic_indicators (series_code, period_date);",
    "CREATE INDEX IF NOT EXISTS idx_ei_source ON raw.economic_indicators (source);",
    "CREATE INDEX IF NOT EXISTS idx_remit_date ON raw.ofw_remittances (period_date);",
    "CREATE INDEX IF NOT EXISTS idx_remit_source ON raw.ofw_remittances (source);",
]

# ── Upsert SQL ────────────────────────────────────────────────────────────────

_UPSERT_INDICATORS = """
INSERT INTO raw.economic_indicators
    (source, series_code, series_name, period_date, frequency,
     value, unit, country_code, notes)
VALUES %s
ON CONFLICT (source, series_code, period_date) DO UPDATE SET
    series_name  = EXCLUDED.series_name,
    value        = EXCLUDED.value,
    unit         = EXCLUDED.unit,
    notes        = EXCLUDED.notes,
    loaded_at    = NOW();
"""

_UPSERT_REMITTANCES = """
INSERT INTO raw.ofw_remittances
    (source, period_date, frequency, remittance_usd, remittance_pct_gdp,
     country_destination, ofw_count, notes)
VALUES %s
ON CONFLICT (source, period_date, country_destination) DO UPDATE SET
    remittance_usd     = EXCLUDED.remittance_usd,
    remittance_pct_gdp = EXCLUDED.remittance_pct_gdp,
    ofw_count          = EXCLUDED.ofw_count,
    notes              = EXCLUDED.notes,
    loaded_at          = NOW();
"""


# ── Module-level helpers (exported for testing) ───────────────────────────────

def _to_indicator_values(
    records: list[EconomicIndicator],
) -> list[tuple[Any, ...]]:
    """Convert EconomicIndicator records to psycopg2 execute_values tuples."""
    return [
        (
            r.source.value,
            r.series_code,
            r.series_name,
            r.period_date,
            r.frequency.value,
            float(r.value) if r.value is not None else None,
            r.unit,
            r.country_code,
            r.notes,
        )
        for r in records
    ]


def _to_remittance_values(
    records: list[OFWRemittance],
) -> list[tuple[Any, ...]]:
    """Convert OFWRemittance records to psycopg2 execute_values tuples."""
    return [
        (
            r.source.value,
            r.period_date,
            r.frequency.value,
            float(r.remittance_usd) if r.remittance_usd is not None else None,
            float(r.remittance_pct_gdp) if r.remittance_pct_gdp is not None else None,
            r.country_destination,
            r.ofw_count,
            r.notes,
        )
        for r in records
    ]


# ── Loader ────────────────────────────────────────────────────────────────────

class WarehouseLoader:
    """
    PostgreSQL warehouse loader for the Philippine economic tracker.

    Usage:
        with WarehouseLoader() as loader:
            loader.upsert_indicators(records)
            loader.upsert_remittances(remittances)
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or settings.postgres_dsn
        self._conn: Any = None

    def __enter__(self) -> "WarehouseLoader":
        self._conn = psycopg2.connect(self._dsn)
        self._conn.autocommit = False
        self._bootstrap()
        safe = self._dsn.split("@")[-1] if "@" in self._dsn else self._dsn
        console.print(f"[dim]PostgreSQL:[/] {safe}")
        return self

    def __exit__(self, *_: Any) -> None:
        if self._conn:
            self._conn.close()

    def _bootstrap(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_DDL_SCHEMA)
            cur.execute(_DDL_ECONOMIC_INDICATORS)
            cur.execute(_DDL_OFW_REMITTANCES)
            for idx_sql in _DDL_INDEXES:
                cur.execute(idx_sql)
        self._conn.commit()

    def upsert_indicators(self, records: list[EconomicIndicator]) -> int:
        if not records:
            return 0
        values = _to_indicator_values(records)
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, _UPSERT_INDICATORS, values, page_size=500
            )
        self._conn.commit()
        console.print(f"[bold green]✓[/] Upserted [bold]{len(records)}[/] indicator rows")
        return len(records)

    def upsert_remittances(self, records: list[OFWRemittance]) -> int:
        if not records:
            return 0
        values = _to_remittance_values(records)
        with self._conn.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, _UPSERT_REMITTANCES, values, page_size=500
            )
        self._conn.commit()
        console.print(f"[bold green]✓[/] Upserted [bold]{len(records)}[/] remittance rows")
        return len(records)

    def indicator_count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw.economic_indicators")
            result = cur.fetchone()
        return int(result[0]) if result else 0

    def remittance_count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM raw.ofw_remittances")
            result = cur.fetchone()
        return int(result[0]) if result else 0

    def fetch_dataframe(self, query: str) -> pl.DataFrame:
        """Execute an arbitrary SELECT and return a Polars DataFrame."""
        with self._conn.cursor() as cur:
            cur.execute(query)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
        return pl.DataFrame(rows, schema=cols, orient="row")
