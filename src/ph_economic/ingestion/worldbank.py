"""
World Bank Indicators API client.

Endpoint pattern:
  GET https://api.worldbank.org/v2/country/PH/indicator/{code}
      ?format=json&per_page=100&mrv=25

Series fetched:
  NY.GDP.MKTP.CD   — GDP at current prices (USD) — annual
  NY.GDP.MKTP.KD.ZG — GDP growth rate (%) — annual
  FP.CPI.TOTL.ZG   — CPI inflation, consumer prices (%) — annual
  BX.TRF.PWKR.CD.DT — Personal remittances received (current USD) — annual
  BX.TRF.PWKR.DT.GD.ZS — Remittances as % of GDP — annual

The World Bank API is free, no auth required, and highly reliable.
Responses are paginated; this client handles all pages automatically.
"""

from __future__ import annotations

from typing import Any

import httpx
from rich.console import Console
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ph_economic.config import settings
from ph_economic.models import (
    DataSource,
    EconomicIndicator,
    Frequency,
    OFWRemittance,
)

console = Console()

# Indicator definitions: code → (series_name, unit, model_type)
_ECONOMIC_INDICATORS: dict[str, tuple[str, str]] = {
    "NY.GDP.MKTP.CD": (
        "GDP at current prices",
        "current USD",
    ),
    "NY.GDP.MKTP.KD.ZG": (
        "GDP growth rate",
        "percent annual",
    ),
    "NY.GDP.PCAP.CD": (
        "GDP per capita (current USD)",
        "current USD",
    ),
    "FP.CPI.TOTL.ZG": (
        "CPI inflation, consumer prices",
        "percent annual",
    ),
    "SL.UEM.TOTL.ZS": (
        "Unemployment rate (% of total labor force)",
        "percent",
    ),
}

_REMITTANCE_INDICATORS: dict[str, str] = {
    "BX.TRF.PWKR.CD.DT": "remittance_usd",
    "BX.TRF.PWKR.DT.GD.ZS": "remittance_pct_gdp",
}


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=settings.retry_base_delay, min=2, max=30),
    reraise=True,
)
def _fetch_page(
    client: httpx.Client,
    indicator: str,
    page: int = 1,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Fetch one page of World Bank indicator data for Philippines.
    Returns (metadata_dict, list_of_data_points).
    """
    url = (
        f"{settings.world_bank_base_url}/country/PH/indicator/{indicator}"
        f"?format=json&per_page={settings.world_bank_per_page}&page={page}"
    )
    response = client.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()

    # World Bank returns [metadata, data] array
    if not isinstance(payload, list) or len(payload) < 2:
        return {}, []
    return payload[0], payload[1] or []


def _fetch_all_pages(
    client: httpx.Client, indicator: str
) -> list[dict[str, Any]]:
    """Fetch all paginated results for a World Bank indicator."""
    meta, first_page = _fetch_page(client, indicator, page=1)
    total_pages = int(meta.get("pages", 1))
    results = list(first_page)

    for page in range(2, total_pages + 1):
        _, page_data = _fetch_page(client, indicator, page=page)
        results.extend(page_data)

    return results


def _parse_economic_indicators(
    raw: list[dict[str, Any]],
    series_code: str,
    series_name: str,
    unit: str,
) -> list[EconomicIndicator]:
    """Parse World Bank data points into EconomicIndicator records."""
    records: list[EconomicIndicator] = []
    for point in raw:
        if point.get("value") is None:
            continue
        year = point.get("date", "")
        if not year or int(year) < settings.start_year:
            continue
        try:
            record = EconomicIndicator(
                source=DataSource.WORLD_BANK,
                series_code=series_code,
                series_name=series_name,
                period_date=year,
                frequency=Frequency.ANNUAL,
                value=point["value"],
                unit=unit,
                country_code="PH",
            )
            records.append(record)
        except Exception as exc:
            console.print(f"  [dim]WB skip {year}: {exc}[/]")
    return records


def _parse_remittances(
    raw_usd: list[dict[str, Any]],
    raw_pct: list[dict[str, Any]],
) -> list[OFWRemittance]:
    """
    Merge USD and % of GDP remittance series into OFWRemittance records.
    Keyed by year — both series cover the same years.
    """
    usd_by_year: dict[str, Any] = {
        p["date"]: p["value"] for p in raw_usd if p.get("value") is not None
    }
    pct_by_year: dict[str, Any] = {
        p["date"]: p["value"] for p in raw_pct if p.get("value") is not None
    }

    all_years = sorted(set(usd_by_year) | set(pct_by_year))
    records: list[OFWRemittance] = []

    for year in all_years:
        if int(year) < settings.start_year:
            continue
        usd_val = usd_by_year.get(year)
        pct_val = pct_by_year.get(year)
        if usd_val is None and pct_val is None:
            continue
        try:
            record = OFWRemittance(
                source=DataSource.WORLD_BANK,
                period_date=year,
                frequency=Frequency.ANNUAL,
                remittance_usd=usd_val,
                remittance_pct_gdp=pct_val,
                country_destination="ALL",
                notes="World Bank WDI — personal remittances received",
            )
            records.append(record)
        except Exception as exc:
            console.print(f"  [dim]WB remittance skip {year}: {exc}[/]")

    return records


class WorldBankClient:
    """
    Client for the World Bank Indicators API.

    Fetches GDP, CPI, employment, and OFW remittance series for Philippines.
    All data is annual, free, no authentication required.

    Usage:
        with WorldBankClient() as client:
            indicators = client.fetch_all_indicators()
            remittances = client.fetch_remittances()
    """

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    def __enter__(self) -> "WorldBankClient":
        self._client = httpx.Client(
            timeout=httpx.Timeout(30),
            follow_redirects=True,
        )
        return self

    def __exit__(self, *_: Any) -> None:
        if self._client:
            self._client.close()

    def fetch_indicator(self, code: str) -> list[EconomicIndicator]:
        """Fetch a single World Bank indicator series."""
        if self._client is None:
            raise RuntimeError("WorldBankClient not initialised — use as context manager: with WorldBankClient() as client")
        if code not in _ECONOMIC_INDICATORS:
            raise ValueError(f"Unknown indicator code: {code!r}")

        series_name, unit = _ECONOMIC_INDICATORS[code]
        console.print(f"  [cyan]→[/] World Bank fetching {code}...")
        try:
            raw = _fetch_all_pages(self._client, code)
            records = _parse_economic_indicators(raw, code, series_name, unit)
            console.print(f"    [green]✓[/] {len(records)} records")
            return records
        except Exception as exc:
            console.print(f"    [yellow]⚠ World Bank {code} failed: {exc}[/]")
            return []

    def fetch_all_indicators(self) -> list[EconomicIndicator]:
        """Fetch all configured economic indicator series."""
        all_records: list[EconomicIndicator] = []
        for code in _ECONOMIC_INDICATORS:
            all_records.extend(self.fetch_indicator(code))
        return all_records

    def fetch_remittances(self) -> list[OFWRemittance]:
        """Fetch OFW remittance series (USD + % of GDP) and merge."""
        if self._client is None:
            raise RuntimeError("WorldBankClient not initialised — use as context manager: with WorldBankClient() as client")
        console.print("  [cyan]→[/] World Bank fetching OFW remittances...")
        try:
            raw_usd = _fetch_all_pages(self._client, "BX.TRF.PWKR.CD.DT")
            raw_pct = _fetch_all_pages(self._client, "BX.TRF.PWKR.DT.GD.ZS")
            records = _parse_remittances(raw_usd, raw_pct)
            console.print(f"    [green]✓[/] {len(records)} remittance records")
            return records
        except Exception as exc:
            console.print(f"    [yellow]⚠ World Bank remittances failed: {exc}[/]")
            return []
