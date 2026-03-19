"""Tests for ph_economic.models — Pydantic validation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from ph_economic.models import (
    DataSource,
    EconomicIndicator,
    Frequency,
    OFWRemittance,
)


class TestEconomicIndicator:

    def test_valid_annual_record(self) -> None:
        r = EconomicIndicator(
            source=DataSource.WORLD_BANK,
            series_code="ny.gdp.mktp.cd",
            series_name="GDP",
            period_date=date(2023, 1, 1),
            frequency=Frequency.ANNUAL,
            value=Decimal("437000000000"),
            unit="current USD",
        )
        # series_code uppercased by validator
        assert r.series_code == "NY.GDP.MKTP.CD"
        assert r.country_code == "PH"

    def test_period_date_from_year_string(self) -> None:
        r = EconomicIndicator(
            source=DataSource.WORLD_BANK,
            series_code="TEST",
            series_name="Test",
            period_date="2022",  # type: ignore[arg-type]
            frequency=Frequency.ANNUAL,
            value=Decimal("100"),
            unit="index",
        )
        assert r.period_date == date(2022, 1, 1)

    def test_period_date_from_quarter_string(self) -> None:
        r = EconomicIndicator(
            source=DataSource.PSA,
            series_code="GDP_Q",
            series_name="Quarterly GDP",
            period_date="2023Q2",  # type: ignore[arg-type]
            frequency=Frequency.QUARTERLY,
            value=Decimal("500"),
            unit="PHP millions",
        )
        assert r.period_date == date(2023, 4, 1)

    def test_period_date_from_yyyymm(self) -> None:
        r = EconomicIndicator(
            source=DataSource.PSA,
            series_code="CPI",
            series_name="CPI",
            period_date="2023-06",  # type: ignore[arg-type]
            frequency=Frequency.MONTHLY,
            value=Decimal("115.2"),
            unit="index",
        )
        assert r.period_date == date(2023, 6, 1)

    def test_null_value_allowed(self) -> None:
        r = EconomicIndicator(
            source=DataSource.WORLD_BANK,
            series_code="TEST",
            series_name="Test",
            period_date=date(2020, 1, 1),
            frequency=Frequency.ANNUAL,
            value=None,
            unit="",
        )
        assert r.value is None

    def test_value_from_string(self) -> None:
        r = EconomicIndicator(
            source=DataSource.WORLD_BANK,
            series_code="TEST",
            series_name="Test",
            period_date=date(2020, 1, 1),
            frequency=Frequency.ANNUAL,
            value="12345.67",  # type: ignore[arg-type]
            unit="",
        )
        assert r.value == Decimal("12345.67")

    def test_missing_value_string_becomes_none(self) -> None:
        r = EconomicIndicator(
            source=DataSource.WORLD_BANK,
            series_code="TEST",
            series_name="Test",
            period_date=date(2020, 1, 1),
            frequency=Frequency.ANNUAL,
            value="..",  # type: ignore[arg-type]
            unit="",
        )
        assert r.value is None

    def test_data_source_enum_values(self) -> None:
        assert DataSource.PSA.value == "PSA"
        assert DataSource.WORLD_BANK.value == "WORLD_BANK"
        assert DataSource.BSP.value == "BSP"


class TestOFWRemittance:

    def test_valid_record(self, sample_remittance: OFWRemittance) -> None:
        assert sample_remittance.remittance_usd == Decimal("38000000000")
        assert sample_remittance.country_destination == "ALL"

    def test_requires_at_least_one_value(self) -> None:
        with pytest.raises(ValueError, match="At least one"):
            OFWRemittance(
                source=DataSource.WORLD_BANK,
                period_date=date(2023, 1, 1),
                frequency=Frequency.ANNUAL,
                remittance_usd=None,
                remittance_pct_gdp=None,
            )

    def test_period_date_from_year_string(self) -> None:
        r = OFWRemittance(
            source=DataSource.WORLD_BANK,
            period_date="2020",  # type: ignore[arg-type]
            frequency=Frequency.ANNUAL,
            remittance_usd=Decimal("30000000000"),
        )
        assert r.period_date == date(2020, 1, 1)

    def test_pct_gdp_only_is_valid(self) -> None:
        r = OFWRemittance(
            source=DataSource.WORLD_BANK,
            period_date=date(2022, 1, 1),
            frequency=Frequency.ANNUAL,
            remittance_pct_gdp=Decimal("9.1"),
        )
        assert r.remittance_usd is None
        assert r.remittance_pct_gdp == Decimal("9.1")

    def test_dotdot_value_becomes_none(self) -> None:
        r = OFWRemittance(
            source=DataSource.BSP,
            period_date=date(2022, 1, 1),
            frequency=Frequency.MONTHLY,
            remittance_usd="..",  # type: ignore[arg-type]
            remittance_pct_gdp=Decimal("8.0"),
        )
        assert r.remittance_usd is None
