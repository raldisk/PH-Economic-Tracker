"""
Tests for ph_economic.loader — PostgreSQL schema and upsert logic.

Unit tests run always (schema validation, dict conversion).
Integration tests require a live PostgreSQL connection via pg_loader fixture.
"""

from __future__ import annotations

import pytest

from ph_economic.loader import WarehouseLoader, _to_indicator_values, _to_remittance_values
from ph_economic.models import EconomicIndicator, OFWRemittance
from tests.conftest import requires_postgres


class TestValueConverters:
    """Unit tests — no DB needed."""

    def test_indicator_to_values_tuple(
        self, sample_indicator: EconomicIndicator
    ) -> None:
        rows = _to_indicator_values([sample_indicator])
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == "WORLD_BANK"        # source
        assert row[1] == "NY.GDP.MKTP.CD"    # series_code
        assert row[4] == "ANNUAL"            # frequency

    def test_remittance_to_values_tuple(
        self, sample_remittance: OFWRemittance
    ) -> None:
        rows = _to_remittance_values([sample_remittance])
        assert len(rows) == 1
        row = rows[0]
        assert row[0] == "WORLD_BANK"        # source
        assert row[6] == "ALL"               # country_destination

    def test_empty_list_returns_empty(self) -> None:
        assert _to_indicator_values([]) == []
        assert _to_remittance_values([]) == []

    def test_null_value_preserved(
        self, sample_indicator: EconomicIndicator
    ) -> None:
        sample_indicator.value = None
        rows = _to_indicator_values([sample_indicator])
        assert rows[0][5] is None            # value column index


@pytest.mark.integration
class TestWarehouseLoaderIntegration:
    """Integration tests — require live PostgreSQL."""

    @requires_postgres
    def test_bootstrap_creates_schema(self, pg_loader: WarehouseLoader) -> None:
        with pg_loader as loader:
            count = loader.indicator_count()
        assert isinstance(count, int)

    @requires_postgres
    def test_upsert_indicators(
        self,
        pg_loader: WarehouseLoader,
        multi_indicators: list[EconomicIndicator],
    ) -> None:
        with pg_loader as loader:
            # Truncate first for test isolation
            with loader._conn.cursor() as cur:
                cur.execute("TRUNCATE raw.economic_indicators CASCADE;")
            loader._conn.commit()

            inserted = loader.upsert_indicators(multi_indicators)
            assert inserted == len(multi_indicators)
            assert loader.indicator_count() == len(multi_indicators)

    @requires_postgres
    def test_upsert_is_idempotent(
        self,
        pg_loader: WarehouseLoader,
        multi_indicators: list[EconomicIndicator],
    ) -> None:
        """ON CONFLICT DO UPDATE — running twice should not create duplicates."""
        with pg_loader as loader:
            with loader._conn.cursor() as cur:
                cur.execute("TRUNCATE raw.economic_indicators CASCADE;")
            loader._conn.commit()

            loader.upsert_indicators(multi_indicators)
            loader.upsert_indicators(multi_indicators)  # second run
            count = loader.indicator_count()

        assert count == len(multi_indicators)

    @requires_postgres
    def test_upsert_remittances(
        self,
        pg_loader: WarehouseLoader,
        multi_remittances: list[OFWRemittance],
    ) -> None:
        with pg_loader as loader:
            with loader._conn.cursor() as cur:
                cur.execute("TRUNCATE raw.ofw_remittances CASCADE;")
            loader._conn.commit()

            inserted = loader.upsert_remittances(multi_remittances)
            assert inserted == len(multi_remittances)
            assert loader.remittance_count() == len(multi_remittances)

    @requires_postgres
    def test_fetch_dataframe(
        self,
        pg_loader: WarehouseLoader,
        multi_indicators: list[EconomicIndicator],
    ) -> None:
        with pg_loader as loader:
            with loader._conn.cursor() as cur:
                cur.execute("TRUNCATE raw.economic_indicators CASCADE;")
            loader._conn.commit()
            loader.upsert_indicators(multi_indicators)
            df = loader.fetch_dataframe(
                "SELECT series_code, COUNT(*) as cnt "
                "FROM raw.economic_indicators GROUP BY series_code"
            )
        assert len(df) == 1
        assert df["cnt"][0] == len(multi_indicators)
