#!/usr/bin/env bash
# Full data refresh: OpenAlex snapshot -> marts -> serving.duckdb -> redeployed API.
# Run monthly by systemd/cu-research-refresh.timer (see docs/DEPLOYMENT.md); safe to
# run by hand. The live site is only touched by the final `docker compose` step, so a
# failure anywhere earlier leaves the deployed image untouched.
#
# Requires on the host: `uv`, `docker`, and gcloud auth (GSM secrets for the lake).
# CU_OPENALEX_LAKE_BACKEND=postgres is set by the systemd unit, never in .env.
set -euo pipefail
cd "$(dirname "$0")/.."

log() { echo "[refresh $(date '+%F %T')] $*"; }

log "1/6 OpenAlex pipeline (authors + works; incremental from the works watermark)"
uv run python -m cu_openalex.flows.pipeline
log "2/6 OpenAlex dimensions (institutions/sources/funders/topics)"
uv run python -m cu_openalex.flows.dimensions_flow
log "3/6 NIH RePORTER grants mart (from cdsci-lake)"
uv run --extra lake python -m cu_openalex.cancer_center.reporter
log "4/6 cancer-center marts (iCite enrichment from cdsci-lake)"
uv run --extra lake python -m cu_openalex.cancer_center.build --no-bake
log "5/6 membership spine + bake serving.duckdb (freshness stamps included)"
uv run --extra lake python -m cu_openalex.cancer_center.membership --no-bake
uv run --extra lake python -m cu_openalex.cancer_center.bake
log "6/6 rebuild + redeploy the API image"
docker compose up -d --build api

# Verify the deployed API is serving the DB we just baked.
built=$(uv run python -c "import duckdb;print(duckdb.connect('data/cancer_center/serving.duckdb',read_only=True).execute(\"select value from dataset_meta where key='built_at'\").fetchone()[0])")
for _ in $(seq 1 30); do
  live=$(docker compose exec -T api python -c "import json,urllib.request;print(json.load(urllib.request.urlopen('http://localhost:8000/api/meta'))['data_freshness'].get('built_at',''))" 2>/dev/null || true)
  [ "$live" = "$built" ] && { log "done: live built_at=$live"; exit 0; }
  sleep 5
done
log "ERROR: live built_at='$live' != baked '$built'"
exit 1
