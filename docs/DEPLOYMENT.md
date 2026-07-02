# Deployment runbook

Production deploy of the cancer-center research-intelligence app via
`docker compose`, fronted by the center's existing **Traefik**.

- **Live URL:** <https://insights.uccc.cancerdatasci.org>
- **Stack:** `web` (nginx: SPA + reverse-proxy `/api`) → `api` (FastAPI + DuckDB,
  internal-only). The serving DuckDB (marts + FTS index) is baked into the API
  image at build time — no data mount, no database server, no runtime lake access
  (ADR-0014, ADR-0017, ADR-0023).

## Host conventions (this server)

These match the shared Traefik in `monode/infrastructure/compose/traefik` and are
**not** the generic defaults shipped in older versions of `docker-compose.yml`:

| Thing | Value | Why |
| --- | --- | --- |
| External Docker network | `proxy` | The network the shared Traefik is attached to. |
| TLS cert resolver | `cloudflare` | An ACME (Let's Encrypt) resolver using the **TLS-ALPN-01** challenge. Despite the name it is *not* DNS-01 and needs no Cloudflare API token. |
| HTTPS entrypoint | `websecure` (:443) | `web` (:80) auto-redirects to it. |
| Hostname umbrella | `<app>.uccc.cancerdatasci.org` | This app is `insights`; router/service labels are app-scoped (`uccc-insights`) so sibling apps coexist. |
| Auth middleware (optional) | `dashboard-auth@file` | Existing basicAuth in Traefik's `config/auth.yml`. |

## DNS (required before TLS will issue)

Add **one A record** at the `cancerdatasci.org` DNS provider (Cloudflare):

| Type | Name | Value | Proxy |
| --- | --- | --- | --- |
| A | `*.uccc` (or the specific `insights.uccc`) | `140.226.4.71` (host `bond0` IP) | **DNS only / gray-cloud** |

**Gray-cloud is mandatory.** TLS-ALPN-01 requires the origin to terminate TLS on
:443 directly; a Cloudflare orange-cloud proxy intercepts :443 and the challenge
fails. The wildcard lets future `<app>.uccc.cancerdatasci.org` apps resolve with
no further DNS changes.

Verify propagation (this host blocks outbound UDP/53, so normal `nslookup
1.1.1.1` times out — use DNS-over-HTTPS over :443 instead):

```bash
curl -s -H 'accept: application/dns-json' \
  'https://1.1.1.1/dns-query?name=insights.uccc.cancerdatasci.org&type=A'
# Expect Status:0 and "data":"140.226.4.71" (the origin IP → gray-cloud)
```

## Deploy

The baked serving database must exist on the host at
`data/cancer_center/serving.duckdb` before building the API image — it is **baked
into the image** at build time, not mounted (ADR-0023). Build it from cdsci-lake
using the `cdsci.lake` accessor (the `lake` extra) against the shared Postgres
store (`CU_OPENALEX_LAKE_BACKEND=postgres`, secrets via Google Secret Manager):

```bash
gcloud auth login                                     # once: GSM secret access
export CU_OPENALEX_LAKE_BACKEND=postgres              # or set it in .env
uv run --extra lake python -m cu_openalex.cancer_center.reporter   # NIH grants mart
uv run --extra lake python -m cu_openalex.cancer_center.build      # marts + bakes serving.duckdb
docker compose up -d --build
```

`build` sources its enrichment (iCite RCR + DOI→PMID) from the lake and bakes
`serving.duckdb` automatically. Run `reporter` **before** `build` so the grants
mart is included in the bake (or run `python -m cu_openalex.cancer_center.bake`
again afterward). The lake is only touched here, on the host — the API image
installs the `api` + `app` extras (no `cdsci-lake`) and runs fully offline; the
app-tier secrets are injected as env, not fetched at runtime (see below). That
builds both images and starts the stack; the router is picked up from the `web`
service's Traefik labels — no Traefik restart needed.

### First-time TLS issuance

Traefik issues the per-host cert on demand. If DNS was registered **after** the
`web` container first started, Traefik will be sitting on a cached
`NXDOMAIN` failure and won't retry on its own. Re-emit the router to force a
fresh ACME attempt:

```bash
docker compose up -d --force-recreate web
```

Verify (no `-k` — the cert should be publicly trusted):

```bash
curl -sS -i https://insights.uccc.cancerdatasci.org/api/health   # {"status":"ok","works":...}
echo | openssl s_client -connect 140.226.4.71:443 \
  -servername insights.uccc.cancerdatasci.org 2>/dev/null \
  | openssl x509 -noout -issuer -subject
# issuer=...Let's Encrypt...  subject=CN=insights.uccc.cancerdatasci.org
```

## Operations

**Refresh the data.** The serving DB is baked into the image, so refreshing data
means rebuilding + redeploying the API image (not restarting it). Rebuild the
marts/serving DB on the host, then rebuild the image:

```bash
export CU_OPENALEX_LAKE_BACKEND=postgres
uv run --extra lake python -m cu_openalex.cancer_center.build   # re-bakes serving.duckdb
docker compose up -d --build api
```

Each deployed image is thus a reproducible, pinned snapshot of the data. (If you
ever need to refresh without rebuilding the image, mount the file read-only —
`./data/cancer_center/serving.duckdb:/app/data/cancer_center/serving.duckdb:ro` —
the fallback noted in ADR-0023.)

**Enable the NL→SQL chat (`/api/chat`).** Provide a server-side Gemini key — end
users never supply one. Create `.env` (gitignored) next to the compose file:

```
GEMINI_API_KEY=...
# optional: CU_OPENALEX_CHAT_MODEL=gemini-2.5-flash
```

Then `docker compose up -d`. Without the key, every other endpoint still works;
only `/api/chat` is disabled.

**Enable the application backend — Google OIDC auth + editable profiles**
(ADR-0026). The `api` image already includes the `app` extra; the tier stays
dormant until an overlay DB password is present. Turn it on in four steps:

1. **Register the OIDC redirect URI.** In the Google Cloud console for the OAuth
   client (`cancerdatasci-oauth-*`), add this exact authorized redirect URI:

   ```
   https://insights.uccc.cancerdatasci.org/api/auth/callback
   ```

   Login is restricted server-side to the `cuanschutz.edu` hosted domain.

2. **Inject the secrets as env** (resolved from GSM on the host; the runtime
   container never contacts GSM). Append them to the deploy `.env` (gitignored):

   ```bash
   gcloud auth login                                   # secret-accessor on cdsci-infra
   bash scripts/fetch-app-secrets.sh >> .env           # DB pw + OIDC client + session key
   echo 'UCCC_APP_ADMIN_EMAILS=sean.2.davis@cuanschutz.edu' >> .env  # seed the first admin
   ```

3. **Overlay Postgres reachability — already wired.** `docker-compose.yml`
   attaches `api` to the shared Postgres network (`pg` → external
   `pg_main_stack_default`) and points `UCCC_APP_DB_HOST` at the `pg_main`
   service, so the container reaches the dedicated `uccc_app` database directly
   (**not** the shared `lake` catalog). On a host where the Postgres lives
   elsewhere, override `UCCC_APP_DB_HOST` and the `pg` network name. If the
   overlay is ever unreachable the app tier degrades to disabled and the read-only
   analytics API keeps serving.

4. **Deploy:** `docker compose up -d --build`. Verify:

   ```bash
   curl -sS https://insights.uccc.cancerdatasci.org/api/app/health   # {"status":"ok",...}
   curl -sSI https://insights.uccc.cancerdatasci.org/api/auth/login  # 302 → accounts.google.com
   ```

   Then sign in at `/api/auth/login`; the admin email above is granted the `admin`
   role on first login. The public analytics stay open; only the write/auth routes
   sit behind the session. To fully disable the tier, leave `UCCC_APP_DB_PASSWORD`
   unset — the API serves read-only analytics exactly as before.

**Gate behind auth** (recommended for the EAB/leadership audience). Uncomment the
middleware label in `docker-compose.yml` and apply:

```yaml
- "traefik.http.routers.uccc-insights.middlewares=dashboard-auth@file"
```

```bash
docker compose up -d
```

**Logs / status:**

```bash
docker compose ps
docker compose logs -f web api
docker logs --since 5m traefik 2>&1 | grep -iE 'insights|acme|certificate'
```

## Adding another app under the umbrella

1. Give its `web` (or equivalent) service Traefik labels with **app-scoped** router
   and service names — e.g. `uccc-<app>` — and rule
   `Host(\`<app>.uccc.cancerdatasci.org\`)`, entrypoint `websecure`, resolver
   `cloudflare`.
2. Attach it to the external `proxy` network.
3. The wildcard `*.uccc` DNS record already covers it; the cert issues on first hit
   (use the `--force-recreate` nudge if DNS lagged the container start).

## Troubleshooting

- **Browser shows a `CloudFlare Origin Certificate`** (subject `CN=CloudFlare
  Origin Certificate`): the real ACME cert hasn't issued; Traefik is serving its
  fallback default cert. Re-run the `--force-recreate web` nudge and confirm DNS
  resolves to `140.226.4.71` via the DoH check above.
- **ACME `NXDOMAIN looking up A`** in `docker logs traefik`: the record wasn't
  visible to Let's Encrypt when Traefik tried. Confirm DNS, then force-recreate.
- **502 from the public URL**: `api` container down or unhealthy — check
  `docker compose logs api` and `GET /api/health` (returns 503 until the curated
  tables are readable).
