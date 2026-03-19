"""
Domain models for the Philippine economic tracker.

EconomicIndicator  — generic time-series record (GDP, CPI, employment, etc.)
OFWRemittance      — OFW-specific remittance record with enriched fields
DataSource         — enum of ingestion sources
Frequency          — enum of reporting frequencies
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class DataSource(str, Enum):
    PSA = "PSA"                    # Philippine Statistics Authority
    BSP = "BSP"                    # Bangko Sentral ng Pilipinas
    WORLD_BANK = "WORLD_BANK"      # World Bank Indicators API


class Frequency(str, Enum):
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUAL = "ANNUAL"


# ── Economic Indicator ────────────────────────────────────────────────────────

class EconomicIndicator(BaseModel):
    """
    Generic time-series record for any PSA or World Bank indicator.
    Covers GDP, CPI, inflation rate, employment, population growth.

    Upsert key: (source, series_code, period_date)
    """

    source: DataSource
    series_code: str = Field(
        description="Indicator code. e.g. 'NY.GDP.MKTP.CD', 'CPI_ALL_ITEMS_2018'."
    )
    series_name: str = Field(description="Human-readable indicator name.")
    period_date: date = Field(
        description="The reference date for this data point. "
        "For quarterly: first day of quarter. For annual: Jan 1."
    )
    frequency: Frequency
    value: Decimal | None = Field(
        default=None, description="Indicator value. None if data is missing."
    )
    unit: str = Field(
        default="",
        description="Unit of measurement. e.g. 'USD', 'percent', 'index (2018=100)'.",
    )
    country_code: str = Field(default="PH", max_length=3)
    notes: str | None = None

    @field_validator("series_code")
    @classmethod
    def strip_series_code(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("value", mode="before")
    @classmethod
    def parse_value(cls, v: Any) -> Decimal | None:
        if v is None or v == "" or v == "..":
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    @field_validator("period_date", mode="before")
    @classmethod
    def parse_period_date(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            # Handle "2024", "2024Q1", "2024-01", "2024-01-01"
            v = v.strip()
            if len(v) == 4:
                return date(int(v), 1, 1)
            if "Q" in v.upper():
                year, q = v.upper().split("Q")
                month = (int(q) - 1) * 3 + 1
                return date(int(year), month, 1)
            if len(v) == 7:
                year, month = v.split("-")
                return date(int(year), int(month), 1)
        raise ValueError(f"Cannot parse period_date: {v!r}")


# ── OFW Remittance ────────────────────────────────────────────────────────────

class OFWRemittance(BaseModel):
    """
    OFW remittance record with enriched economic context fields.

    Primary source: World Bank BX.TRF.PWKR.CD.DT (annual, current USD)
    Secondary: BSP monthly data when available.

    Upsert key: (source, period_date, country_destination)
    """

    source: DataSource
    period_date: date
    frequency: Frequency
    remittance_usd: Decimal | None = Field(
        default=None,
        description="Total remittances received in current USD.",
    )
    remittance_pct_gdp: Decimal | None = Field(
        default=None,
        description="Remittances as % of GDP.",
    )
    country_destination: str = Field(
        default="ALL",
        description="Destination country ISO code, or 'ALL' for aggregate.",
    )
    ofw_count: int | None = Field(
        default=None, description="Number of OFWs in this period if available."
    )
    notes: str | None = None

    @field_validator("remittance_usd", "remittance_pct_gdp", mode="before")
    @classmethod
    def parse_decimal(cls, v: Any) -> Decimal | None:
        if v is None or v == "" or v == "..":
            return None
        try:
            return Decimal(str(v))
        except Exception:
            return None

    @field_validator("period_date", mode="before")
    @classmethod
    def parse_period_date(cls, v: Any) -> date:
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v = v.strip()
            if len(v) == 4:
                return date(int(v), 1, 1)
            if len(v) == 7:
                year, month = v.split("-")
                return date(int(year), int(month), 1)
        raise ValueError(f"Cannot parse period_date: {v!r}")

    @model_validator(mode="after")
    def at_least_one_value(self) -> "OFWRemittance":
        if self.remittance_usd is None and self.remittance_pct_gdp is None:
            raise ValueError(
                "At least one of remittance_usd or remittance_pct_gdp must be provided."
            )
        return self
