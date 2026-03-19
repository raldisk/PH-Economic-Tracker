#!/bin/bash
set -e

# ── Wait for PostgreSQL ───────────────────────────────────────────────────────
echo "[entrypoint] Waiting for PostgreSQL at ${PH_TRACKER_PG_HOST:-postgres}:${PH_TRACKER_PG_PORT:-5432}..."

until pg_isready \
    -h "${PH_TRACKER_PG_HOST:-postgres}" \
    -p "${PH_TRACKER_PG_PORT:-5432}" \
    -U "${PH_TRACKER_PG_USER:-tracker}" \
    -q; do
  sleep 1
done

echo "[entrypoint] PostgreSQL is ready."

# ── Dispatch ──────────────────────────────────────────────────────────────────
COMMAND="${1:-ingest}"

case "$COMMAND" in
  ingest)
    echo "[entrypoint] Running pipeline ingestion..."
    exec ph-tracker ingest "${@:2}"
    ;;
  transform)
    echo "[entrypoint] Running dbt transforms..."
    exec ph-tracker transform "${@:2}"
    ;;
  status)
    echo "[entrypoint] Checking warehouse status..."
    exec ph-tracker status
    ;;
  streamlit)
    echo "[entrypoint] Starting Streamlit dashboard on :8501..."
    exec streamlit run /app/dashboard/app.py \
      --server.port=8501 \
      --server.address=0.0.0.0 \
      --server.headless=true \
      --browser.gatherUsageStats=false
    ;;
  shell)
    exec /bin/bash
    ;;
  *)
    echo "[entrypoint] Unknown command: $COMMAND"
    echo "Usage: $0 {ingest|transform|status|streamlit|shell}"
    exit 1
    ;;
esac
