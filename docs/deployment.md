# Showcase deployment: DigitalOcean + Docker Compose

This guide is for the repository's `compose.yaml`. No hosting resources have been
created and no public URL is claimed to be live. You will perform deployment.

## Why this setup

Use one DigitalOcean Ubuntu Droplet with Docker, Caddy, and a domain you control.
This fits the current SQLite architecture: one API process, persistent local
storage, and one HTTPS origin. A small VPS requires OS patching and backups;
it avoids splitting this showcase across multiple platforms. Start with 2 vCPUs
and 4 GB RAM, then check actual usage during rehearsal before choosing capacity.
Check DigitalOcean's current price before purchasing; no plan price is assumed.

Official references:

- [DigitalOcean Docker image](https://docs.digitalocean.com/products/marketplace/catalog/docker/)
- [Create and connect to a Droplet](https://docs.digitalocean.com/products/droplets/getting-started/quickstart/)
- [Recommended Droplet security setup](https://docs.digitalocean.com/products/droplets/getting-started/recommended-droplet-setup/)
- [Enable backups](https://docs.digitalocean.com/products/backups/getting-started/quickstart/)
- [Caddy automatic HTTPS and DNS requirements](https://caddyserver.com/docs/automatic-https)

## 1. Prepare the release and server

### Chosen address: seniorprojectteamscience.com

The intended production address is **https://seniorprojectteamscience.com/**.
The poster destination is **https://seniorprojectteamscience.com/showcase**.
The owner is purchasing the domain; ownership, DNS and live hosting have not yet
been verified. `teamscience.com` is no longer the requested deployment address.

After purchasing `seniorprojectteamscience.com`, create these records at the
registrar's DNS provider (DigitalOcean DNS is optional):

| Type | Name | Value |
| --- | --- | --- |
| A | `@` | Your Droplet's public IPv4 address |
| CNAME | `www` | `seniorprojectteamscience.com` |

Remove conflicting A/AAAA/CNAME records for these two names. Preserve unrelated
mail verification and MX records. Set `.env` to
`DOMAIN=seniorprojectteamscience.com`. The supplied Caddy configuration redirects
`www.seniorprojectteamscience.com` to the bare domain and manages HTTPS for both.
Both DNS names must resolve before certificate issuance. No domain purchase or
DNS changes have been performed by this agent.

See [DigitalOcean domain setup](https://docs.digitalocean.com/products/networking/dns/how-to/add-domains/).

### Release and server steps

1. Merge reviewed feature PRs into `main`. Require both CI jobs to pass.
2. In GitHub create `production` from that green `main` commit. This checkout was
   on `prod` when the work began; it is not evidence that `production` exists or
   has passed CI. Do not rename it blindly or deploy unreviewed local changes.
3. Protect `main` and `production` in Settings → Rules → Rulesets: require PRs,
   passing Backend tests and Frontend typecheck and build, and block force pushes
   and deletion. Promote via a `main` → `production` PR. Avoid squash promotion
   if it would repeatedly diverge the branches.
4. Create an Ubuntu Droplet using the Docker marketplace image. Add your SSH key
   and enable backups. Use the provider's setup guide to create your operator user.
5. In a DigitalOcean Cloud Firewall allow SSH (22) from your IP, and HTTP/HTTPS
   (80/443) from the internet. Do not expose 8000 or 3000. Only Caddy publishes ports.
6. Add an A record such as `seniorprojectteamscience.com` pointing to the Droplet IP.
   Remove stale AAAA records unless IPv6 is configured. Wait for DNS to resolve.

## 2. Configure secrets and build

SSH to the server. Run the following from a directory owned by your operator user:

```bash
git clone https://github.com/Poiixen/senior_design.git
cd senior_design
git switch production
cp deploy/env.example .env
chmod 600 .env
openssl rand -hex 32
```

Edit `.env`: set `DOMAIN` to the hostname only (no scheme/path) and set
`SECRET_KEY` to the generated value. Keep it stable across upgrades and store a
backup in your password manager. Never commit `.env`. Changing this secret signs
every visitor out. The Compose file requires a value but cannot judge its entropy.

```bash
docker compose config --quiet
docker compose build
docker compose run --rm api python -m scripts.seed_showcase
docker compose up -d
docker compose ps
curl --fail https://seniorprojectteamscience.com/health
```

Expected health response: `{"status":"ok"}`. Caddy obtains and renews the TLS
certificate when DNS and ports are correct. Open `/showcase` on the same hostname.
No `VITE_API_BASE_URL` is needed: `/api/*` and `/health` go to FastAPI; all other
paths go to the React Router server, including direct links and refreshes.

## Configuration and limits

| Setting | Supplied by Compose | Meaning |
| --- | --- | --- |
| `SECRET_KEY` | `.env` | Persistent session-signing secret |
| `SESSION_COOKIE_SECURE` | `true` | Cookies sent over HTTPS only |
| `DATABASE_PATH` | `/data/analysis.sqlite3` | SQLite metadata |
| `DATASET_STORAGE_DIR` | `/data/datasets` | Parquet rows by dataset ID |
| `CORS_ALLOWED_ORIGINS` | `https://${DOMAIN}` | Exact public origin; PATCH supported |
| `SHOWCASE_ENABLED` | `true` | Enables password-free read-only demo entry |
| `PUBLIC_RATE_LIMITS` | `true` | Per-client limits: 20 auth / 30 other write requests per minute |
| `MAX_UPLOAD_SIZE` | `10485760` | 10 MB upload cap; Caddy allows 11 MB for multipart overhead |

API command: `uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 1`
with proxy headers, a concurrency cap of 32 and a five-second keepalive timeout.
Docker restarts stopped services automatically; no development `--reload` is used.
The frontend Dockerfile runs `npm ci`, `npm run build`, then `npm run start`.

The API is limited to 2 GB RAM / 1.5 CPUs and the frontend to 512 MB RAM. Log files
rotate at 10 MB with three retained files per service. Caddy allows 120 seconds
for API response headers. Compressed spreadsheets can expand beyond upload size;
the memory and concurrency limits contain impact but do not guarantee every large
upload succeeds. Rehearse with your actual data. One SQLite writer is appropriate
for a small showcase, not unrestricted production scale.

Rate limits are bounded in-memory safeguards for one API process, reset on restart,
and shared by visitors behind the same IP. If you add workers/replicas or need
stronger abuse protection, replace them with a shared limiter or edge service.
Uvicorn trusts forwarded IP headers because the API has no published port and is
reachable through the trusted Compose proxy. Do not publish the API directly.

AI credentials are intentionally absent from Compose. Core reports and demo
suggestions work without them. Personal report chat reports unavailability when
no key is configured. If enabling AI later, inject `ANTHROPIC_API_KEY` server-side
only and review usage limits; demo suggestions never call AI and demo chat is blocked.

## 3. Rehearse before printing the QR

Use a phone on cellular data, then test iOS Safari and Android Chrome:

1. Open `/showcase`, tap **Try Demo**, inspect the overview, expand a saved
   comparison and check its chart, then read suggestions. No upload is required.
2. Refresh `/showcase/report`; the saved data must still load. Follow the full
   report link and verify saved comparisons. Rotate the phone and test narrow widths.
3. Leave idle for five minutes, then retry via `/showcase`. Do not extend personal
   sessions just for the booth; demo re-entry takes one tap.
4. Log out, register a personal test user, upload a small CSV, save a comparison,
   generate suggestions, refresh and confirm user-scoped history. Verify unavailable
   chat is understandable without a key. Inspect Secure/HttpOnly session cookies.
5. Record report IDs and comparison counts. Run `docker compose restart`, then
   `docker compose up -d --force-recreate`. Repeat those checks. Both must preserve
   SQLite and associated Parquet files; the named `app-data` volume stores both.
6. Verify demo mutations receive 403 and another user's reports receive 404.

Only after this passes, generate a QR for the exact final HTTPS `/showcase` URL.
Export SVG or a large PNG with a four-module quiet zone, print a test at the final
poster size, and scan it with several cameras. Include the written URL and
“Tap Try Demo — no upload needed.” No QR has been generated for a placeholder URL.

## Updates, backup, rollback, and staging

Before promotion, run CI and rehearse in a separate Droplet/domain with its own
secret and volume. Never point staging at production storage. CI also runs on
`production`; hosting deployment is a deliberate manual step, not an automatic SSH job.

Record the current commit (`git rev-parse HEAD`) in your release notes. For a
consistent backup, stop writers and archive the entire data volume together:

```bash
mkdir -p backups
docker compose stop api
docker compose run --rm --no-deps --user root -v "$PWD/backups:/backup" api \
  sh -c 'tar -czf /backup/app-data.tgz -C /data .'
docker compose start api
```

Copy that archive off the Droplet and retain dated versions. It includes user data;
restrict access. Provider backups are useful additional protection, not a substitute
for testing restore. Never run `docker compose down -v`: it erases named volumes.

To deploy: `git fetch origin`, `git switch production`, `git pull --ff-only`,
`docker compose build`, then `docker compose up -d`. Run `/health` and the workflow
above. Run the seed command again if needed; it reuses the demo report and repairs
a missing demo Parquet file without duplicating comparisons. Run only one seeder
at a time, during maintenance; do not seed against a live changing database.

To roll back code, `git switch --detach <previous-tested-commit>`, rebuild and
`docker compose up -d`. This change adds no database columns. For future schema
changes check compatibility before rolling code back. Keep the same `.env` and
volume. For disaster recovery, restore the archive into a new empty data volume
while the API is stopped, preserving ownership UID 10001, then start the matching
code version. Test that both saved reports and comparisons work after restoration.

For demo credential rotation, no shared password exists: a random Argon2-hashed
password is created offline and discarded. Disable entry with `SHOWCASE_ENABLED=false`
if needed. Rotating `SECRET_KEY` invalidates existing sessions. Canonical demo data
is immutable through the API; reseeding restores a lost Parquet file. Do not delete
production tables to reset the demo; use a fresh isolated staging volume for a full reset.

Troubleshooting: `docker compose logs --tail=100 api frontend proxy` and
`docker stats`. For TLS failures check DNS and 80/443; for login failures check
HTTPS and cookie settings; for missing rows check the volume and dataset path.
Schedule OS security updates and test backups before the showcase.
