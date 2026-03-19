"""
Shared pytest fixtures.

Unit fixtures (always available):
  sample_indicator, sample_remittance, multi_indicators

Integration fixtures (require live PostgreSQL):
  pg_loader — WarehouseLoader connected to test DB
  pg_dsn    — DSN string from environment
"""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest

from ph_economic.models import (
    DataSource,
    EconomicIndicator,
    Frequency,
    OFWRemittance,
)


# ── PostgreSQL availability ───────────────────────────────────────────────────

def _pg_dsn() -> str | None:
    return os.environ.get("PH_TRACKER_POSTGRES_DSN") or os.environ.get("DATABASE_URL")


def _pg_available() -> bool:
    dsn = _pg_dsn()
    if not dsn:
        return False
    try:
        import psycopg2
        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


requires_postgres = pytest.mark.skipif(
    not _pg_available(),
    reason="PostgreSQL not reachable — set PH_TRACKER_POSTGRES_DSN to enable",
)


# ── Domain model fixtures ─────────────────────────────────────────────────────

@pytest.fixture
def sample_indicator() -> EconomicIndicator:
    return EconomicIndicator(
        source=DataSource.WORLD_BANK,
        series_code="NY.GDP.MKTP.CD",
        series_name="GDP at current prices",
        period_date=date(2023, 1, 1),
        frequency=Frequency.ANNUAL,
        value=Decimal("437146000000"),
        unit="current USD",
        country_code="PH",
    )


@pytest.fixture
def sample_remittance() -> OFWRemittance:
    return OFWRemittance(
        source=DataSource.WORLD_BANK,
        period_date=date(2023, 1, 1),
        frequency=Frequency.ANNUAL,
        remittance_usd=Decimal("38000000000"),
        remittance_pct_gdp=Decimal("8.7"),
        country_destination="ALL",
    )


@pytest.fixture
def multi_indicators() -> list[EconomicIndicator]:
    years = range(2015, 2025)
    return [
        EconomicIndicator(
            source=DataSource.WORLD_BANK,
            series_code="NY.GDP.MKTP.CD",
            series_name="GDP at current prices",
            period_date=date(year, 1, 1),
            frequency=Frequency.ANNUAL,
            value=Decimal(str(300_000_000_000 + year * 5_000_000_000)),
            unit="current USD",
            country_code="PH",
        )
        for year in years
    ]


@pytest.fixture
def multi_remittances() -> list[OFWRemittance]:
    years = range(2015, 2025)
    return [
        OFWRemittance(
            source=DataSource.WORLD_BANK,
            period_date=date(year, 1, 1),
            frequency=Frequency.ANNUAL,
            remittance_usd=Decimal(str(28_000_000_000 + year * 500_000_000)),
            remittance_pct_gdp=Decimal("8.5"),
            country_destination="ALL",
        )
        for year in years
    ]


# ── PostgreSQL fixtures (guarded) ─────────────────────────────────────────────

@pytest.fixture
def pg_dsn() -> str:
    dsn = _pg_dsn()
    if not dsn:
        pytest.skip("PH_TRACKER_POSTGRES_DSN not set")
    return dsn


@pytest.fixture
def pg_loader(pg_dsn: str):  # type: ignore[return]
    """
    WarehouseLoader connected to the test database.

    Yield-based so teardown always runs — truncates both tables after
    every test, preventing stale data from leaking into the next test.
    Previously the fixture returned an un-entered loader; tests that
    called TRUNCATE at the START of each test would silently inherit
    leftover rows if a prior test failed mid-run.
    """
    from ph_economic.loader import WarehouseLoader
    with WarehouseLoader(dsn=pg_dsn) as loader:
        yield loader
        # Teardown: always truncate regardless of test outcome
        try:
            with loader._conn.cursor() as cur:
                cur.execute(
                    "TRUNCATE raw.economic_indicators, raw.ofw_remittances CASCADE;"
                )
            loader._conn.commit()
        except Exception:
            pass  # schema may not exist yet on first bootstrap test
