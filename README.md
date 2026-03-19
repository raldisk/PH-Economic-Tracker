# ph-economic-tracker

**Philippine PSA economic indicators + OFW remittance pipeline.**

Ingests GDP, CPI, employment, and OFW remittance data from the PSA OpenSTAT API and World Bank WDI, loads into PostgreSQL, transforms with dbt, and serves an interactive Streamlit dashboard — all deployable locally via a single `docker compose up`.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![dbt-postgres](https://img.shields.io/badge/dbt-postgres-orange.svg)](https://docs.getdbt.com/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35+-FF4B4B.svg)](https://streamlit.io/)

> **Full setup instructions → [USAGE.md](USAGE.md)**
> Local Python setup and Docker setup are documented separately with step-by-step commands.


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

## Data Sources

| Source | Series | Frequency | API |
|---|---|---|---|
| PSA OpenSTAT | CPI All Items (2018=100) | Monthly | PXWeb REST |
| PSA OpenSTAT | CPI YoY inflation rate | Monthly | PXWeb REST |
| World Bank WDI | GDP at current prices | Annual | Indicators REST |
| World Bank WDI | GDP growth rate | Annual | Indicators REST |
| World Bank WDI | GDP per capita | Annual | Indicators REST |
| World Bank WDI | CPI inflation | Annual | Indicators REST |
| World Bank WDI | Unemployment rate | Annual | Indicators REST |
| World Bank WDI | OFW remittances (USD) | Annual | Indicators REST |
| World Bank WDI | Remittances % of GDP | Annual | Indicators REST |
| BSP | OFW remittances monthly | Monthly | CSV download (optional) |

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

## What I'd Improve With More Time

- **Monthly GDP from PSA** — wire the quarterly PSA PXWeb GDP tables directly; currently using World Bank annual data as primary.
- **Scheduled ingestion** — add a GitHub Actions cron workflow or a simple APScheduler in the pipeline service to auto-refresh weekly.
- **Forecast layer** — a simple ARIMA or Prophet model on the remittance series would demonstrate ML integration on top of the warehouse.
- **dbt incremental models** — switch from full-refresh to incremental with `unique_key` as data volume grows.
- **Alert layer** — Telegram notification when a key indicator crosses a threshold (e.g. inflation > 6%).

---

## License

MIT
