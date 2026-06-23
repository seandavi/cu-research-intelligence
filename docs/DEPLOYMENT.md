# Deployment runbook

Production deploy of the cancer-center research-intelligence app via
`docker compose`, fronted by the center's existing **Traefik**.

- **Live URL:** <https://insights.uccc.cancerdatasci.org>
- **Stack:** `web` (nginx: SPA + reverse-proxy `/api`) → `api` (FastAPI + DuckDB,
  internal-only). Curated Parquet mounted read-only; no database server
  (ADR-0014, ADR-0017).

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

The curated tables must already exist on the host under `data/cancer_center/`
(built with `uv run python -m cu_openalex.cancer_center.build`; mounted read-only).

```bash
docker compose up -d --build
```

That builds both images and starts the stack. The router is picked up from the
`web` service's Traefik labels — no Traefik restart needed.

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

**Refresh the data.** Rebuild the curated tables on the host, then restart the
API (the mount is read-only; nginx/SPA are unaffected):

```bash
uv run python -m cu_openalex.cancer_center.build
docker compose restart api
```

**Enable the NL→SQL chat (`/api/chat`).** Provide a server-side Gemini key — end
users never supply one. Create `.env` (gitignored) next to the compose file:

```
GEMINI_API_KEY=...
# optional: CU_OPENALEX_CHAT_MODEL=gemini-2.5-flash
```

Then `docker compose up -d`. Without the key, every other endpoint still works;
only `/api/chat` is disabled.

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
