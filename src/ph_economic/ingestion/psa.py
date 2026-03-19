"""
PSA OpenSTAT PXWeb API client.

Targets the PSA PXWeb REST API:
  Base: https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB

Key series fetched:
  - CPI All Items (2018=100) — monthly
  - CPI Year-on-Year change (inflation rate) — monthly
  - GDP at current prices (quarterly)

PXWeb API pattern:
  GET /DB/{path}/{table}.px — returns table metadata + data in JSON
  POST /DB/{path}/{table}.px — POST with variable filter for specific series
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from rich.console import Console
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ph_economic.config import settings
from ph_economic.models import DataSource, EconomicIndicator, Frequency

console = Console()

# PXWeb table paths on PSA OpenSTAT
# Verified from: https://openstat.psa.gov.ph/PXWeb/pxweb/en/DB/
_CPI_TABLE = "DB__2M__PI__CPI__2018/0012M4PCPIAa.px"
_CPI_YOY_TABLE = "DB__2M__PI__CPI__2018/0022M4PCPIAb.px"

# World Bank is the primary GDP source — PSA GDP via PXWeb requires
# complex multi-variable POST filters that vary by table version.
# We flag this and fall back gracefully.
_GDP_TABLE = "DB__2B__NA__QA__2018/0012BNAQGDPe.px"

_SERIES_MAP = {
    "CPI_ALL_ITEMS": {
        "table": _CPI_TABLE,
        "series_name": "Consumer Price Index - All Items (2018=100)",
        "unit": "index (2018=100)",
        "frequency": Frequency.MONTHLY,
    },
    "CPI_YOY_CHANGE": {
        "table": _CPI_YOY_TABLE,
        "series_name": "CPI Year-on-Year Change - All Items",
        "unit": "percent",
        "frequency": Frequency.MONTHLY,
    },
}


def _build_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=settings.retry_base_delay, min=2, max=30),
    reraise=True,
)
def _fetch_table_metadata(client: httpx.Client, table_path: str) -> dict[str, Any]:
    """Fetch PXWeb table metadata (variables, values, time range)."""
    url = f"{settings.psa_base_url}/{table_path}"
    response = client.get(url, headers=_build_headers())
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
    stop=stop_after_attempt(settings.max_retries),
    wait=wait_exponential(multiplier=settings.retry_base_delay, min=2, max=30),
    reraise=True,
)
def _fetch_table_data(
    client: httpx.Client, table_path: str, query: dict[str, Any]
) -> dict[str, Any]:
    """POST a PXWeb query to fetch filtered table data."""
    url = f"{settings.psa_base_url}/{table_path}"
    response = client.post(url, json=query, headers=_build_headers())
    response.raise_for_status()
    return response.json()  # type: ignore[no-any-return]


def _parse_pxweb_response(
    data: dict[str, Any],
    series_code: str,
    series_name: str,
    unit: str,
    frequency: Frequency,
) -> list[EconomicIndicator]:
    """
    Parse a PXWeb JSON-stat response into EconomicIndicator records.

    PXWeb returns data in JSON-stat format:
    {
      "dataset": {
        "value": [...],
        "dimension": {
          "id": ["Geolocation", "Time"],
          "size": [N, T],
          "Geolocation": {"category": {"index": {...}, "label": {...}}},
          "Time": {"category": {"index": {...}, "label": {...}}}
        }
      }
    }
    """
    records: list[EconomicIndicator] = []

    try:
        dataset = data.get("dataset") or data
        dimension = dataset.get("dimension", {})
        values = dataset.get("value", [])

        # Find the Time dimension.
        # PSA PXWeb dimension naming is not standardized across tables —
        # CPI uses "Time", others use "Year", "Month", "Period", or locale
        # variants. We match on common patterns; if none match we emit a
        # diagnostic warning with the actual dimension names found so that
        # debugging doesn't require reading PSA table metadata manually.
        dim_ids: list[str] = dimension.get("id", [])
        time_dim_key = next(
            (
                d for d in dim_ids
                if any(t in d.lower() for t in ("time", "year", "month", "period"))
            ),
            None,
        )
        if not time_dim_key:
            console.print(
                f"  [yellow]⚠ PSA: no time dimension found in {series_code}.[/] "
                f"Available dimensions: {dim_ids!r}. "
                "Expected one of: 'Time', 'Year', 'Month', 'Period'. "
                "Update the detection pattern in psa.py if the table uses a different name."
            )
            return records

        time_labels: dict[str, str] = (
            dimension.get(time_dim_key, {})
            .get("category", {})
            .get("label", {})
        )

        # For national-level data, PSA often has only Philippines as geo
        # We take the first geo slice which is national totals
        time_count = len(time_labels)
        geo_count = len(values) // time_count if time_count else 1

        # Values are laid out as [geo0_t0, geo0_t1, ..., geo1_t0, ...]
        # We want geo index 0 (PHILIPPINES national total)
        national_values = values[:time_count] if geo_count > 1 else values

        for idx, (time_code, time_label) in enumerate(time_labels.items()):
            if idx >= len(national_values):
                break
            raw_value = national_values[idx]

            try:
                record = EconomicIndicator(
                    source=DataSource.PSA,
                    series_code=series_code,
                    series_name=series_name,
                    period_date=time_label,  # PXWeb labels are "2024M01" etc.
                    frequency=frequency,
                    value=raw_value,
                    unit=unit,
                    country_code="PH",
                )
                records.append(record)
            except Exception as exc:
                console.print(f"  [dim]PSA skip {time_label}: {exc}[/]")
                continue

    except Exception as exc:
        console.print(f"  [red]PSA parse error for {series_code}: {exc}[/]")

    return records


def _build_national_query(metadata: dict[str, Any]) -> dict[str, Any]:
    """
    Build a PXWeb query that selects Philippines-national data for all time periods.
    """
    dataset = metadata.get("dataset") or metadata
    dimension = dataset.get("dimension", {})
    dim_ids: list[str] = dimension.get("id", [])

    variables = []
    for dim_id in dim_ids:
        dim_info = dimension.get(dim_id, {})
        cat = dim_info.get("category", {})
        index_dict = cat.get("index", {})
        all_codes = list(index_dict.keys())

        if "geo" in dim_id.lower() or "location" in dim_id.lower():
            # Select only first code = PHILIPPINES national
            selected = [all_codes[0]] if all_codes else all_codes
        else:
            # Select all codes for time / commodity
            selected = all_codes

        variables.append({
            "code": dim_id,
            "selection": {"filter": "item", "values": selected},
        })

    return {"query": variables, "response": {"format": "json-stat"}}


class PSAClient:
    """
    Client for the PSA OpenSTAT PXWeb API.

    Fetches CPI (monthly) and attempts GDP quarterly.
    GDP is supplemented by World Bank data — see worldbank.py.

    Usage:
        with PSAClient() as client:
            records = client.fetch_cpi()
    """

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    def __enter__(self) -> "PSAClient":
        self._client = httpx.Client(
            timeout=httpx.Timeout(settings.psa_request_timeout),
            follow_redirects=True,
        )
        return self

    def __exit__(self, *_: Any) -> None:
        if self._client:
            self._client.close()

    def _fetch_series(self, series_key: str) -> list[EconomicIndicator]:
        if self._client is None:
            raise RuntimeError("PSAClient not initialised — use as context manager: with PSAClient() as client")
        meta = _SERIES_MAP[series_key]
        table_path = meta["table"]

        console.print(f"  [cyan]→[/] PSA fetching {series_key}...")
        try:
            metadata = _fetch_table_metadata(self._client, table_path)
            query = _build_national_query(metadata)
            data = _fetch_table_data(self._client, table_path, query)
            records = _parse_pxweb_response(
                data,
                series_code=series_key,
                series_name=meta["series_name"],  # type: ignore[arg-type]
                unit=meta["unit"],  # type: ignore[arg-type]
                frequency=meta["frequency"],  # type: ignore[arg-type]
            )
            console.print(f"    [green]✓[/] {len(records)} records")
            return records
        except Exception as exc:
            console.print(f"    [yellow]⚠ PSA {series_key} failed: {exc}[/]")
            return []

    def fetch_cpi(self) -> list[EconomicIndicator]:
        """Fetch CPI All Items (2018=100) monthly series."""
        return self._fetch_series("CPI_ALL_ITEMS")

    def fetch_cpi_yoy(self) -> list[EconomicIndicator]:
        """Fetch CPI Year-on-Year inflation rate monthly series."""
        return self._fetch_series("CPI_YOY_CHANGE")

    def fetch_all(self) -> list[EconomicIndicator]:
        """Fetch all configured PSA series."""
        records: list[EconomicIndicator] = []
        records.extend(self.fetch_cpi())
        records.extend(self.fetch_cpi_yoy())
        return records
