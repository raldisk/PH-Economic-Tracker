"""
Configuration management via pydantic-settings.
All values are overridable via environment variables or a .env file.
Prefix: PH_TRACKER_
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PH_TRACKER_",
        extra="ignore",
    )

    # --- PostgreSQL warehouse ---------------------------------------------
    postgres_dsn: str = Field(
        default="postgresql://tracker:tracker@localhost:5432/ph_economic",
        description="Full DSN for PostgreSQL. Set PH_TRACKER_POSTGRES_DSN.",
    )

    # --- PSA OpenSTAT PXWeb API -------------------------------------------
    psa_base_url: str = Field(
        default="https://openstat.psa.gov.ph/PXWeb/api/v1/en/DB",
        description="Base URL for the PSA OpenSTAT PXWeb API.",
    )
    psa_request_timeout: int = Field(
        default=60,
        description="HTTP timeout for PSA API calls (seconds). PSA can be slow.",
    )

    # --- World Bank API ---------------------------------------------------
    world_bank_base_url: str = Field(
        default="https://api.worldbank.org/v2",
        description="Base URL for the World Bank Indicators API.",
    )
    world_bank_per_page: int = Field(
        default=100,
        description="Records per page for World Bank API pagination.",
    )

    # --- Ingestion --------------------------------------------------------
    max_retries: int = Field(default=3, description="Max HTTP retry attempts.")
    retry_base_delay: float = Field(
        default=2.0, description="Base delay (seconds) for exponential backoff."
    )
    start_year: int = Field(
        default=2000,
        description="Earliest year to fetch for historical series.",
    )

    # --- Pipeline ---------------------------------------------------------
    dbt_project_dir: str = Field(
        default="transforms",
        description="Path to the dbt project directory.",
    )
    dbt_profiles_dir: str = Field(
        default="transforms",
        description="Path to the directory containing dbt profiles.yml.",
    )


settings = Settings()
