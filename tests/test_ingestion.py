"""
Tests for ingestion clients — World Bank and BSP.

All HTTP calls are mocked with respx so no live API is needed.
BSP tests use a temporary CSV file.
"""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import respx

from ph_economic.ingestion.bsp import BSPClient
from ph_economic.ingestion.worldbank import WorldBankClient, _parse_remittances
from ph_economic.models import DataSource, Frequency, OFWRemittance


# ── World Bank fixtures ───────────────────────────────────────────────────────

def _wb_response(indicator: str, data: list[dict]) -> dict:
    """Build a minimal World Bank API response envelope."""
    return [
        {"page": 1, "pages": 1, "per_page": 100, "total": len(data)},
        data,
    ]


_SAMPLE_GDP_DATA = [
    {"date": "2023", "value": 437146000000.0},
    {"date": "2022", "value": 404282000000.0},
    {"date": "2021", "value": 394086000000.0},
    {"date": "2020", "value": 361489000000.0},
    {"date": "2019", "value": 376823000000.0},
]

_SAMPLE_REMIT_USD = [
    {"date": "2023", "value": 37200000000.0},
    {"date": "2022", "value": 36142000000.0},
    {"date": "2021", "value": 34882000000.0},
]

_SAMPLE_REMIT_PCT = [
    {"date": "2023", "value": 8.51},
    {"date": "2022", "value": 8.94},
    {"date": "2021", "value": 8.85},
]


# ── World Bank tests ──────────────────────────────────────────────────────────

class TestWorldBankClient:

    @respx.mock
    def test_fetch_gdp_indicator(self) -> None:
        """Mocked World Bank GDP fetch returns correctly parsed records."""
        url_pattern = respx.get(
            "https://api.worldbank.org/v2/country/PH/indicator/NY.GDP.MKTP.CD"
        ).respond(
            200,
            json=_wb_response("NY.GDP.MKTP.CD", _SAMPLE_GDP_DATA),
        )

        with WorldBankClient() as client:
            records = client.fetch_indicator("NY.GDP.MKTP.CD")

        assert len(records) == 5
        assert records[0].series_code == "NY.GDP.MKTP.CD"
        assert records[0].source == DataSource.WORLD_BANK
        assert records[0].frequency == Frequency.ANNUAL
        assert records[0].value is not None

    @respx.mock
    def test_fetch_gdp_filters_below_start_year(self) -> None:
        """Records with year < start_year should be excluded."""
        old_data = [{"date": "1990", "value": 44000000000.0}]
        respx.get(
            "https://api.worldbank.org/v2/country/PH/indicator/NY.GDP.MKTP.CD"
        ).respond(200, json=_wb_response("NY.GDP.MKTP.CD", old_data))

        with WorldBankClient() as client:
            records = client.fetch_indicator("NY.GDP.MKTP.CD")

        assert len(records) == 0

    @respx.mock
    def test_fetch_gdp_skips_null_values(self) -> None:
        """Data points with null value should be silently skipped."""
        data_with_nulls = [
            {"date": "2023", "value": None},
            {"date": "2022", "value": 404282000000.0},
        ]
        respx.get(
            "https://api.worldbank.org/v2/country/PH/indicator/NY.GDP.MKTP.CD"
        ).respond(200, json=_wb_response("NY.GDP.MKTP.CD", data_with_nulls))

        with WorldBankClient() as client:
            records = client.fetch_indicator("NY.GDP.MKTP.CD")

        assert len(records) == 1
        assert records[0].value is not None

    @respx.mock
    def test_fetch_remittances_merges_usd_and_pct(self) -> None:
        """Remittances USD + % of GDP should merge into single OFWRemittance records."""
        respx.get(
            "https://api.worldbank.org/v2/country/PH/indicator/BX.TRF.PWKR.CD.DT"
        ).respond(200, json=_wb_response("BX.TRF.PWKR.CD.DT", _SAMPLE_REMIT_USD))

        respx.get(
            "https://api.worldbank.org/v2/country/PH/indicator/BX.TRF.PWKR.DT.GD.ZS"
        ).respond(200, json=_wb_response("BX.TRF.PWKR.DT.GD.ZS", _SAMPLE_REMIT_PCT))

        with WorldBankClient() as client:
            records = client.fetch_remittances()

        assert len(records) == 3
        assert all(r.source == DataSource.WORLD_BANK for r in records)
        assert all(r.remittance_usd is not None for r in records)
        assert all(r.remittance_pct_gdp is not None for r in records)

    def test_parse_remittances_usd_only(self) -> None:
        """Records should still be created when pct_gdp is missing."""
        records = _parse_remittances(_SAMPLE_REMIT_USD, [])
        assert len(records) == 3
        assert all(r.remittance_pct_gdp is None for r in records)

    def test_unknown_indicator_raises(self) -> None:
        with WorldBankClient() as client:
            with pytest.raises(ValueError, match="Unknown indicator"):
                client.fetch_indicator("INVALID.CODE")

    @respx.mock
    def test_http_error_returns_empty_list(self) -> None:
        """On HTTP error, client returns empty list — pipeline continues."""
        respx.get(
            "https://api.worldbank.org/v2/country/PH/indicator/NY.GDP.MKTP.CD"
        ).respond(500)

        with WorldBankClient() as client:
            records = client.fetch_indicator("NY.GDP.MKTP.CD")

        assert records == []


# ── BSP CSV tests ─────────────────────────────────────────────────────────────

class TestBSPClient:

    def test_no_csv_path_returns_empty(self) -> None:
        with BSPClient() as client:
            records = client.fetch_monthly_remittances()
        assert records == []

    def test_missing_csv_path_returns_empty(self) -> None:
        with BSPClient(csv_path="/nonexistent/path.csv") as client:
            records = client.fetch_monthly_remittances()
        assert records == []

    def test_parses_valid_csv(self, tmp_path: Path) -> None:
        """Well-formed BSP-style CSV should parse correctly."""
        csv_content = (
            "Year,Month,Total (USD Millions),Land-based,Sea-based\n"
            "2022,January,2800.5,2200,600\n"
            "2022,February,2650.0,2100,550\n"
            "2022,March,3100.0,2450,650\n"
        )
        csv_file = tmp_path / "bsp_remittances.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        with BSPClient(csv_path=csv_file) as client:
            records = client.fetch_monthly_remittances()

        assert len(records) == 3
        assert all(r.source == DataSource.BSP for r in records)
        assert all(r.frequency == Frequency.MONTHLY for r in records)
        # USD millions → USD, so 2800.5M = 2_800_500_000
        assert records[0].remittance_usd == Decimal("2800500000.000000")

    def test_skips_rows_below_start_year(self, tmp_path: Path) -> None:
        """Rows before settings.start_year should be excluded."""
        csv_content = (
            "Year,Month,Total (USD Millions)\n"
            "1995,January,500.0\n"
            "2022,January,2800.5\n"
        )
        csv_file = tmp_path / "bsp.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        with BSPClient(csv_path=csv_file) as client:
            records = client.fetch_monthly_remittances()

        assert len(records) == 1
        assert records[0].period_date.year == 2022

    def test_skips_malformed_rows_gracefully(self, tmp_path: Path) -> None:
        """Rows with unparseable months or values should be skipped silently."""
        csv_content = (
            "Year,Month,Total (USD Millions)\n"
            "2022,January,2800.5\n"
            "2022,BADMONTH,1000.0\n"
            "2022,March,N/A\n"
            "2022,April,3000.0\n"
        )
        csv_file = tmp_path / "bsp.csv"
        csv_file.write_text(csv_content, encoding="utf-8")

        with BSPClient(csv_path=csv_file) as client:
            records = client.fetch_monthly_remittances()

        # January and April should parse; BADMONTH and N/A should be skipped
        assert len(records) == 2
