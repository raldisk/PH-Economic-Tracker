# Usage Guide — ph-economic-tracker

Two ways to run this project. Both produce the same result: PostgreSQL warehouse
loaded with PSA + World Bank data, dbt marts, and a Streamlit dashboard.

Pick one:

- [Local Python setup](#local-python-setup) — best for development and debugging
- [Docker setup](#docker-setup) — one command, no Python install required

---

## Local Python Setup

### Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.11+ | `python --version` |
| pip | latest | `pip --version` |
| PostgreSQL | 16 (running) | `pg_isready` |
| Git | any | `git --version` |

**Install PostgreSQL 16 locally (if not already running):**

Windows (via installer): https://www.postgresql.org/download/windows/

macOS:
```bash
brew install postgresql@16
brew services start postgresql@16
```

Ubuntu/Debian:
```bash
sudo apt install postgresql-16
sudo systemctl start postgresql
```

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ph-economic-tracker.git
cd ph-economic-tracker
```

---

### Step 2 — Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

Windows (CMD):
```cmd
.venv\Scripts\activate.bat
```

macOS / Linux:
```bash
source .venv/bin/activate
```

You should see `(.venv)` in your prompt.

---

### Step 3 — Install the package

```bash
# Production dependencies only
pip install -r requirements.txt

# OR install as an editable package (recommended for development)
pip install -e .

# With dev/test dependencies
pip install -r requirements-dev.txt
```

Verify the CLI installed:
```bash
ph-tracker --help
```

Expected output:
```
Usage: ph-tracker [OPTIONS] COMMAND [ARGS]...
  Philippine Economic Indicators + OFW Remittance Pipeline
Commands:
  ingest     Fetch data from all sources and load into PostgreSQL.
  transform  Run dbt transforms only.
  status     Print current warehouse statistics.
  reset      Drop and recreate raw schema.
```

---

### Step 4 — Create the PostgreSQL database

Connect to PostgreSQL and create the database and user:

```bash
# Connect as the postgres superuser
psql -U postgres
```

Then inside psql:
```sql
CREATE USER tracker WITH PASSWORD 'tracker';
CREATE DATABASE ph_economic OWNER tracker;
GRANT ALL PRIVILEGES ON DATABASE ph_economic TO tracker;
\q
```

Verify the connection:
```bash
psql -U tracker -d ph_economic -c "SELECT 1;"
```

---

### Step 5 — Configure environment

```bash
cp .env.example .env
```

Open `.env` and verify these values match your PostgreSQL setup:

```bash
PH_TRACKER_POSTGRES_DSN=postgresql://tracker:tracker@localhost:5432/ph_economic
PH_TRACKER_PG_HOST=localhost
PH_TRACKER_PG_PORT=5432
PH_TRACKER_PG_USER=tracker
PH_TRACKER_PG_PASSWORD=tracker
PH_TRACKER_PG_DBNAME=ph_economic
```

If your PostgreSQL uses a different user or password, update all five fields.

---

### Step 6 — Run the pipeline

**Full run (ingest all sources → load → dbt transforms):**
```bash
ph-tracker ingest
```

This will:
1. Fetch CPI monthly data from PSA OpenSTAT
2. Fetch GDP, inflation, unemployment, and remittance data from World Bank
3. Load everything into `raw.economic_indicators` and `raw.ofw_remittances`
4. Run `dbt run` to build staging views and mart tables
5. Run `dbt test` to validate the mart tables

Expected output (abridged):
```
──────────── Philippine Economic Tracker — Ingest ────────────

PSA OpenSTAT
  → PSA fetching CPI_ALL_ITEMS...
    ✓ 312 records
  → PSA fetching CPI_YOY_CHANGE...
    ✓ 288 records

World Bank API
  → World Bank fetching NY.GDP.MKTP.CD...
    ✓ 24 records
  ...

Loading to PostgreSQL
  ✓ Upserted 650 indicator rows
  ✓ Upserted 24 remittance rows
  Total indicator rows : 650
  Total remittance rows: 24

→ Running dbt transforms...
✓ dbt transforms complete
✓ dbt tests passed
──────────── Ingest complete ────────────
```

**Partial runs (useful during development):**
```bash
# PSA only
ph-tracker ingest --source psa

# World Bank only
ph-tracker ingest --source worldbank

# Load data but skip dbt
ph-tracker ingest --skip-dbt

# With optional BSP monthly CSV
ph-tracker ingest --source bsp --bsp-csv data/bsp_ofw_remittances.csv
```

---

### Step 7 — Check warehouse status

```bash
ph-tracker status
```

Shows row counts per series and the latest data date per indicator.

---

### Step 8 — Run dbt transforms only

If you've already loaded data and just want to rebuild the mart tables:

```bash
# Use dev profile (connects to localhost)
ph-tracker transform --target dev
```

Or run dbt directly for more control:
```bash
cd transforms
dbt run --profiles-dir . --project-dir . --target dev
dbt test --profiles-dir . --project-dir . --target dev
dbt docs generate --profiles-dir . --project-dir . --target dev
dbt docs serve  # Opens browser at localhost:8080
```

---

### Step 9 — Start the Streamlit dashboard

```bash
streamlit run dashboard/app.py
```

Open your browser at: **http://localhost:8501**

The dashboard connects to PostgreSQL using the same `PH_TRACKER_POSTGRES_DSN`
env var. It auto-refreshes every 5 minutes and has a manual refresh button.

---

### Step 10 — Run tests

```bash
# Unit tests only (no live database needed)
pytest tests/test_models.py tests/test_ingestion.py -v

# All tests including integration (requires live PostgreSQL)
pytest -v

# Coverage report
pytest --cov=ph_economic --cov-report=html
# Then open htmlcov/index.html in your browser
```

---

### Local troubleshooting

**`psycopg2.OperationalError: could not connect to server`**
- PostgreSQL is not running. Start it: `sudo systemctl start postgresql` (Linux) or `brew services start postgresql@16` (macOS)
- Verify: `pg_isready -h localhost -U tracker`

**`dbt: command not found`**
- dbt is installed as part of the package. Ensure your venv is activated.
- Try: `python -m dbt run --profiles-dir transforms --project-dir transforms`

**`ph-tracker: command not found`**
- Run `pip install -e .` to register the CLI entry point.

**PSA API returns empty or errors**
- PSA OpenSTAT can be slow or temporarily unavailable. Run with `--source worldbank` first to verify the rest of the pipeline, then retry PSA later.
- Increase timeout: `PH_TRACKER_PSA_REQUEST_TIMEOUT=120` in `.env`

**dbt `relation "raw.economic_indicators" does not exist`**
- Run `ph-tracker ingest --skip-dbt` first to load data, then `ph-tracker transform`.

---

---

## Docker Setup

### Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Docker | 24+ | `docker --version` |
| Docker Compose | v2 (plugin) | `docker compose version` |
| Git | any | `git --version` |

No Python, no PostgreSQL install needed. Docker handles everything.

> **Windows note:** Use PowerShell or Git Bash. Make sure Docker Desktop is running.

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/ph-economic-tracker.git
cd ph-economic-tracker
```

---

### Step 2 — Configure environment

```bash
cp .env.example .env
```

The default `.env` values work out of the box with Docker. Only change them if
you need different ports (e.g. if 5432 or 8501 are already in use on your machine):

```bash
# Change these only if you have port conflicts
PG_PORT=5432          # PostgreSQL exposed port
STREAMLIT_PORT=8501   # Dashboard port
ADMINER_PORT=8080     # Adminer DB browser port
```

---

### Step 3 — Build the Docker image

```bash
docker compose build
```

This builds a multi-stage image:
- Stage 1 (builder): installs all pip dependencies
- Stage 2 (runtime): copies only installed packages + source, runs as non-root user `tracker`

First build takes ~2–3 minutes (downloading base image + pip packages).
Subsequent builds use Docker layer cache and are much faster.

---

### Step 4 — Start PostgreSQL and Adminer

```bash
docker compose up postgres adminer -d
```

Wait for PostgreSQL to be healthy:
```bash
docker compose ps
```

Expected output:
```
NAME                        STATUS
ph-economic-tracker-postgres-1   Up (healthy)
ph-economic-tracker-adminer-1    Up
```

The `(healthy)` status means PostgreSQL passed its health check and is ready
to accept connections. This usually takes 10–15 seconds on first run.

---

### Step 5 — Run the pipeline

```bash
docker compose run --rm app ingest
```

`--rm` removes the container automatically after it exits.
The `app` service runs the full ingest pipeline (PSA + World Bank + dbt).

To run with specific options:
```bash
# World Bank only
docker compose run --rm app ingest --source worldbank

# Skip dbt transforms
docker compose run --rm app ingest --skip-dbt

# With BSP CSV (mount the file first)
docker compose run --rm \
  -v $(pwd)/data:/app/data \
  app ingest --source bsp --bsp-csv /app/data/bsp_ofw_remittances.csv
```

---

### Step 6 — Check warehouse status

```bash
docker compose run --rm app status
```

---

### Step 7 — Start the Streamlit dashboard

```bash
docker compose up streamlit -d
```

Open your browser at: **http://localhost:8501**

The dashboard service:
- Starts immediately (PostgreSQL health is already confirmed by Step 4)
- Stays running until you stop it
- Auto-reconnects if PostgreSQL restarts

---

### Step 8 — Open Adminer (DB browser)

Open your browser at: **http://localhost:8080**

Login with:
| Field | Value |
|---|---|
| System | PostgreSQL |
| Server | `postgres` |
| Username | `tracker` |
| Password | `tracker` |
| Database | `ph_economic` |

Useful things to explore in Adminer:
- `raw` schema → `economic_indicators` and `ofw_remittances` (raw ingested data)
- `staging` schema → `stg_economic_indicators`, `stg_ofw_remittances` (dbt views)
- `marts` schema → `gdp_trend`, `cpi_trend`, `remittance_trend`, `economic_dashboard`

---

### Step 9 — Run dbt transforms only (Docker)

If you need to rebuild mart tables without re-fetching data:

```bash
docker compose run --rm app transform
```

Or with a specific target:
```bash
docker compose run --rm app transform --target prod
```

---

### Step 10 — Open a shell inside the container (debugging)

```bash
docker compose run --rm app shell
```

From inside the container you can run `ph-tracker` directly, inspect files, or
connect to PostgreSQL:

```bash
# Inside the container
ph-tracker status
psql $PH_TRACKER_POSTGRES_DSN -c "\dt raw.*"
```

---

### Stopping everything

```bash
# Stop all running services (keeps data volumes)
docker compose down

# Stop and DELETE all data (fresh start)
docker compose down -v
```

After `docker compose down -v`, PostgreSQL data is gone. Run `docker compose up postgres -d`
then `docker compose run --rm app ingest` to start fresh.

---

### Viewing logs

```bash
# All services
docker compose logs -f

# PostgreSQL only
docker compose logs -f postgres

# Streamlit only
docker compose logs -f streamlit

# Last 50 lines from app
docker compose logs --tail=50 app
```

---

### Scheduled daily runs (Docker)

To re-run the pipeline daily without GitHub Actions, add a cron job that calls:

Linux/macOS crontab (`crontab -e`):
```cron
# Run every day at 08:00 local time
0 8 * * * cd /path/to/ph-economic-tracker && docker compose run --rm app ingest >> logs/ingest.log 2>&1
```

Windows Task Scheduler — create a task that runs:
```
docker compose run --rm app ingest
```
with working directory set to the project folder.

---

### Docker troubleshooting

**`port is already allocated` (5432, 8501, or 8080)**

Another service is using that port. Change the port in `.env`:
```bash
PG_PORT=5433          # Use 5433 instead of 5432
STREAMLIT_PORT=8502
ADMINER_PORT=8081
```
Then restart: `docker compose down && docker compose up postgres adminer -d`

**`app exited with code 1`**

PostgreSQL wasn't ready in time. The entrypoint waits, but if it still fails:
```bash
docker compose logs app     # Read the full error
docker compose ps postgres  # Check postgres health status
```
If postgres shows `(health: starting)`, wait 15 more seconds and retry.

**Dashboard shows "No data found"**

The mart tables don't exist yet. Run the pipeline first:
```bash
docker compose run --rm app ingest
```

**`docker compose build` fails on pip install**

Clear Docker cache and try again:
```bash
docker compose build --no-cache
```

**Adminer shows "No database selected" or connection refused**

Make sure you're connecting to server `postgres` (the Docker service name),
not `localhost`. Inside Docker, services communicate by their service name.

---

### Full Docker workflow (copy-paste sequence)

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/ph-economic-tracker.git
cd ph-economic-tracker

# 2. Configure
cp .env.example .env

# 3. Build
docker compose build

# 4. Start database + DB browser
docker compose up postgres adminer -d

# 5. Wait ~15 seconds, then run pipeline
docker compose run --rm app ingest

# 6. Start dashboard
docker compose up streamlit -d

# 7. Open browser
# Dashboard  → http://localhost:8501
# DB browser → http://localhost:8080
```

---

## Services at a glance

| Service | URL | What it does |
|---|---|---|
| Dashboard | http://localhost:8501 | Streamlit — GDP, CPI, remittance charts |
| Adminer | http://localhost:8080 | Browse PostgreSQL schemas and tables |
| PostgreSQL | localhost:5432 | Warehouse (internal) |

---

## Useful one-liners (both local and Docker)

```bash
# Re-run pipeline (safe to run repeatedly — upsert is idempotent)
ph-tracker ingest                              # local
docker compose run --rm app ingest            # docker

# Rebuild dbt marts only
ph-tracker transform                           # local
docker compose run --rm app transform         # docker

# Check what's in the warehouse
ph-tracker status                              # local
docker compose run --rm app status            # docker

# Wipe everything and start fresh
ph-tracker reset --confirm                     # local
docker compose down -v && docker compose up postgres -d && docker compose run --rm app ingest   # docker
```
