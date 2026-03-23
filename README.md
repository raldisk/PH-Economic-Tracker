# ph-economic-tracker

**Philippine PSA economic indicators + OFW remittance pipeline.**

Ingests GDP, CPI, employment, and OFW remittance data from the PSA OpenSTAT API and World Bank WDI, loads into PostgreSQL, transforms with dbt, and serves an interactive Streamlit dashboard — all deployable locally via a single `docker compose up`.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![dbt-postgres](https://img.shields.io/badge/dbt-postgres-orange.svg)](https://docs.getdbt.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B.svg)](https://streamlit.io/)

> **Full setup instructions → [USAGE.md](USAGE.md)**
> Local Python setup and Docker setup are documented separately with step-by-step commands.

> **Companion analysis repo → [ph-ofw-analysis](https://github.com/raldisk/ph-ofw-analysis)**
> Jupyter notebook with EDA, STL decomposition, correlation analysis, and a 3-year SARIMAX remittance forecast. Connects directly to this pipeline's PostgreSQL marts when the Docker stack is running.


---

## Preview

![Warehouse Data Snapshot](docs/preview.png)

> Four mart tables visualized: GDP trend + growth rate · OFW remittances + % of GDP · CPI inflation vs BSP target band · GDP per capita 2000–2024. Generated from `marts.economic_dashboard` and `marts.cpi_trend`.

---

## Architecture

![Pipeline Architecture](docs/architecture.svg)

## Dashboard Preview

![Dashboard Preview](docs/dashboard-preview.svg)

---

## Architecture (text)

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Data Sources                                  │
│                                                                        │
│  PSA OpenSTAT PXWeb API        World Bank WDI API      BSP CSV        │
│  openstat.psa.gov.ph           api.worldbank.org       (optional)     │
│  · CPI monthly (2018=100)      · GDP (annual, USD)     · OFW monthly  │
│  · CPI YoY inflation           · GDP growth rate                      │
│                                · GDP per capita                       │
│                                · CPI inflation (annual)               │
│                                · Unemployment rate                    │
│                                · OFW remittances (USD + % GDP)        │
└──────────────────┬───────────────────────┬──────────────────┬─────────┘
                   │                       │                  │
                   └───────────────────────┴──────────────────┘
                                           │
                                           ▼  Pydantic v2 validation
                          ┌────────────────────────────────┐
                          │     INGESTION LAYER             │
                          │  ingestion/psa.py               │
                          │  ingestion/worldbank.py         │
                          │  ingestion/bsp.py               │
                          │  models.py (EconomicIndicator,  │
                          │            OFWRemittance)        │
                          └──────────────┬─────────────────┘
                                         │  upsert ON CONFLICT
                                         ▼
                          ┌────────────────────────────────┐
                          │   PostgreSQL 16 — raw schema    │
                          │   raw.economic_indicators       │
                          │   raw.ofw_remittances           │
                          │   (psycopg2 + execute_values)   │
                          └──────────────┬─────────────────┘
                                         │  dbt run
                                         ▼
                          ┌────────────────────────────────┐
                          │   dbt-postgres transforms       │
                          │                                 │
                          │   staging/                      │
                          │   ├─ stg_economic_indicators    │
                          │   └─ stg_ofw_remittances        │
                          │                                 │
                          │   marts/                        │
                          │   ├─ gdp_trend                  │
                          │   ├─ cpi_trend                  │
                          │   ├─ remittance_trend           │
                          │   └─ economic_dashboard  ◄──┐   │
                          └──────────────────────────┬──┘   │
                                                     │       │
                                         ┌───────────┘       │
                                         ▼                    │
                          ┌──────────────────────────────────┐│
                          │   Streamlit Dashboard (port 8501) ││
                          │   · GDP trend + growth rate       ││
                          │   · CPI + inflation chart          ││
                          │   · OFW remittance trend           ││
                          │   · Metric cards (latest values)   ││
                          │   · Year range filter              ││
                          │   · CSV download per chart         ││
                          └───────────────────────────────────┘│
                                                                │
                          ┌─────────────────────────────────┐  │
                          │   Adminer (port 8080)            │  │
                          │   Browse all schemas directly    │  │
                          └─────────────────────────────────┘  │
```

---

## Quickstart — Docker (recommended)

```bash
git clone https://github.com/YOUR_USERNAME/ph-economic-tracker.git
cd ph-economic-tracker

# Configure (defaults work out of the box)
cp .env.example .env

# Pull + start PostgreSQL and Adminer
docker compose up postgres adminer -d

# Run the full ingestion pipeline
docker compose run --rm app ingest

# Start the Streamlit dashboard
docker compose up streamlit -d
```

Open in your browser:
- **Dashboard**: http://localhost:8501
- **Adminer DB browser**: http://localhost:8080
  - Server: `postgres`, User: `tracker`, Password: `tracker`, Database: `ph_economic`

---

## Quickstart — Local Python

**Prerequisites:** Python 3.11+, PostgreSQL 16 running locally

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# Or with requirements.txt
pip install -r requirements-dev.txt

# Copy and configure environment
cp .env.example .env
# Set PH_TRACKER_POSTGRES_DSN to your local PostgreSQL

# Run pipeline
ph-tracker ingest

# Run dbt transforms only
ph-tracker transform

# Check warehouse status
ph-tracker status

# Start dashboard
streamlit run dashboard/app.py
```

---

## CLI Reference

```bash
ph-tracker ingest                     # Fetch all sources → PostgreSQL → dbt
ph-tracker ingest --source psa        # PSA only
ph-tracker ingest --source worldbank  # World Bank only
ph-tracker ingest --source bsp --bsp-csv data/bsp.csv  # BSP monthly CSV
ph-tracker ingest --skip-dbt          # Load only, skip transforms
ph-tracker transform                  # Run dbt models only
ph-tracker transform --target dev     # Use dev dbt profile
ph-tracker status                     # Show warehouse row counts + latest dates
ph-tracker reset --confirm            # DROP raw schema (destructive)
```

---

## Docker Services

| Service | Port | Description |
|---|---|---|
| `postgres` | 5432 | PostgreSQL 16 warehouse |
| `app` | — | Pipeline runner (exits after ingest) |
| `streamlit` | 8501 | Live interactive dashboard |
| `adminer` | 8080 | Lightweight DB browser UI |

---

## Data Sources & Citations

All data used in this project is sourced from official Philippine government agencies and international institutions. No third-party or proprietary data is required.

| # | Series | Agency | Frequency | Access Method | URL |
|---|---|---|---|---|---|
| 1 | CPI All Items (2018=100) | Philippine Statistics Authority | Monthly | PXWeb REST API | [openstat.psa.gov.ph](https://openstat.psa.gov.ph/) |
| 2 | CPI YoY inflation rate | Philippine Statistics Authority | Monthly | PXWeb REST API | [openstat.psa.gov.ph](https://openstat.psa.gov.ph/) |
| 3 | GDP at current USD prices | World Bank WDI | Annual | Indicators REST API | [api.worldbank.org/v2/](https://api.worldbank.org/v2/) |
| 4 | GDP annual growth rate | World Bank WDI | Annual | Indicators REST API | [api.worldbank.org/v2/](https://api.worldbank.org/v2/) |
| 5 | GDP per capita (USD) | World Bank WDI | Annual | Indicators REST API | [api.worldbank.org/v2/](https://api.worldbank.org/v2/) |
| 6 | OFW remittances (USD + % of GDP) | World Bank WDI | Annual | Indicators REST API | [api.worldbank.org/v2/](https://api.worldbank.org/v2/) |
| 7 | Unemployment rate | World Bank WDI | Annual | Indicators REST API | [api.worldbank.org/v2/](https://api.worldbank.org/v2/) |
| 8 | OFW remittances monthly (optional) | Bangko Sentral ng Pilipinas | Monthly | CSV download / scrape | [bsp.gov.ph/statistics](https://www.bsp.gov.ph/sitepages/statistics/exchangerate.aspx) |

### Full citation details

**Philippine Statistics Authority (PSA) — OpenSTAT**
> Philippine Statistics Authority. *OpenSTAT PXWeb API — Consumer Price Index and related series.*
> Retrieved from `https://openstat.psa.gov.ph/`
> Base year: 2018 = 100. Coverage: January 2000 – present. Updated monthly.

**World Bank — World Development Indicators (WDI)**
> World Bank. *World Development Indicators — GDP, remittances, employment series for the Philippines (PHL).*
> Retrieved from `https://api.worldbank.org/v2/country/PHL/indicator/`
> Indicator codes used: `NY.GDP.MKTP.CD`, `NY.GDP.MKTP.KD.ZG`, `NY.GDP.PCAP.CD`,
> `FP.CPI.TOTL.ZG`, `SL.UEM.TOTL.ZS`, `BX.TRF.PWKR.CD.DT`, `BX.TRF.PWKR.DT.GD.ZS`
> License: CC BY 4.0. No API key required.

**Bangko Sentral ng Pilipinas (BSP) — OFW Remittances**
> Bangko Sentral ng Pilipinas. *Overseas Filipinos' Remittances — monthly data.*
> Retrieved from `https://www.bsp.gov.ph/`
> Note: BSP monthly OFW data is an optional enrichment layer. The core pipeline uses World Bank annual series.
> Accessed via: static HTML tables and downloadable XLSX files.

### Data freshness

| Source | Update cadence | Pipeline refresh |
|---|---|---|
| PSA OpenSTAT CPI | ~3 weeks after reference month | Monthly (GitHub Actions cron) |
| World Bank WDI | Annual (April–May release) | Annual |
| BSP remittances | ~6 weeks after reference month | Monthly (optional) |

---

## dbt Models

### Staging (views — lightweight cleaning)
- `stg_economic_indicators` — null filter, string trim, `indicator_type` classification
- `stg_ofw_remittances` — currency conversion to USD billions, period labelling

### Marts (tables — analytics-ready)
- `gdp_trend` — annual GDP with YoY growth rate and per-capita, computed via `LAG()`
- `cpi_trend` — monthly CPI index + inflation rate with MoM change
- `remittance_trend` — annual OFW totals with YoY growth and 3-year rolling average
- `economic_dashboard` — wide annual table joining all three marts, primary Streamlit source

---

## Project Structure

```
ph-economic-tracker/
├── src/ph_economic/
│   ├── config.py           # Pydantic settings — all env-driven
│   ├── models.py           # EconomicIndicator + OFWRemittance domain models
│   ├── loader.py           # PostgreSQL upsert loader
│   ├── pipeline.py         # Typer CLI (ingest/transform/status/reset)
│   └── ingestion/
│       ├── psa.py          # PSA OpenSTAT PXWeb client
│       ├── worldbank.py    # World Bank Indicators client
│       └── bsp.py          # BSP CSV parser (optional)
├── transforms/             # dbt project
│   ├── models/
│   │   ├── staging/        # stg_economic_indicators, stg_ofw_remittances
│   │   └── marts/          # gdp_trend, cpi_trend, remittance_trend, economic_dashboard
│   ├── dbt_project.yml
│   └── profiles.yml
├── dashboard/
│   └── app.py              # Streamlit dashboard
├── tests/
│   ├── conftest.py         # Fixtures + postgres availability guard
│   ├── test_models.py      # Pydantic validation
│   ├── test_loader.py      # PostgreSQL schema + upsert
│   └── test_ingestion.py   # API clients (respx mocks)
├── scripts/
│   └── entrypoint.sh       # wait-for-postgres + command dispatch
├── Dockerfile              # Multi-stage, pip-based, non-root
├── docker-compose.yml      # postgres + app + streamlit + adminer
├── setup.py                # Installable package
├── requirements.txt        # Production dependencies
├── requirements-dev.txt    # Dev + test dependencies
└── .env.example
```

---

## Testing

```bash
# Unit tests only (no DB needed)
pytest tests/test_models.py tests/test_ingestion.py -v

# Full suite including integration (requires live PostgreSQL)
PH_TRACKER_POSTGRES_DSN=postgresql://tracker:tracker@localhost:5432/ph_economic \
  pytest -v

# Coverage report
pytest --cov=ph_economic --cov-report=html
open htmlcov/index.html
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PH_TRACKER_POSTGRES_DSN` | `postgresql://tracker:tracker@localhost:5432/ph_economic` | Full PostgreSQL DSN |
| `PH_TRACKER_PG_HOST` | `postgres` | PostgreSQL host (for dbt + docker-compose) |
| `PH_TRACKER_PG_USER` | `tracker` | PostgreSQL user |
| `PH_TRACKER_PG_PASSWORD` | `tracker` | PostgreSQL password |
| `PH_TRACKER_PG_DBNAME` | `ph_economic` | Database name |
| `PH_TRACKER_START_YEAR` | `2000` | Earliest year to fetch |
| `PH_TRACKER_MAX_RETRIES` | `3` | HTTP retry attempts |
| `PH_TRACKER_PSA_REQUEST_TIMEOUT` | `60` | PSA API timeout (seconds) |
| `STREAMLIT_PORT` | `8501` | Dashboard port |
| `ADMINER_PORT` | `8080` | Adminer port |

---

## License

MIT
