# Deploy on the existing 512 MB Droplet

**Access policy update:** rebuild both application images and configure SMTP
using [security setup](security.md) before rollout. Shared demo login is disabled;
all product pages require a verified account. Existing deployment archives and
anonymous-showcase instructions below predate this change.

This is a trial configuration for light showcase traffic on a 1 CPU / 512 MB RAM /
10 GB disk Droplet with 1 GB swap. It is not a capacity guarantee. Build on Windows,
then transfer images; do not build on the server. Heavy analyses and simultaneous
uploads may exhaust memory. The original compose.yaml remains available for larger
servers.

## Prepared configuration

`compose.small.yaml` uses prebuilt images, one API worker, single-threaded numeric
libraries, at most eight concurrent API connections, a 1 MiB upload limit and small
rotating logs. API RAM limit is 320 MiB (832 MiB including swap), frontend 96 MiB
(192 MiB including swap), proxy 64 MiB (128 MiB including swap). These are ceilings,
not reserved RAM; the host still needs memory, so physical-Droplet testing matters.
See [Docker memory and swap limits](https://docs.docker.com/engine/containers/resource_constraints/).

The local package is `.run/team-science-deploy.tar.gz`. It contains only the two
application images, Caddy image, compose.small.yaml, Caddyfile and start script.
It contains no uploaded datasets, database or deployment secret.

## 1. Domain and firewall

Confirm the actual Droplet IP in DigitalOcean. The previously supplied IP was
167.99.145.105. A local DNS lookup on November 18 returned 104.207.79.172 instead;
resolve that mismatch before starting Caddy.

In Namecheap Advanced DNS set A `@` to the actual Droplet IPv4 and CNAME `www` to
`spteamscience.com`. Remove conflicting web parking records and stale AAAA records
only for these hosts; preserve mail records. Leave Namecheap BasicDNS selected.

In DigitalOcean attach a Cloud Firewall allowing inbound TCP 22 from your current
IP and TCP 80/443 from the internet. Keep outbound access enabled for certificates
and updates. Do not expose ports 3000 or 8000. If UFW is enabled on Ubuntu, ensure
SSH remains allowed and allow TCP 80/443 there too.

On the server, both commands should resolve to its public IPv4:

```bash
getent ahostsv4 spteamscience.com
getent ahostsv4 www.spteamscience.com
```

## 2. Transfer from Windows PowerShell

These commands assume the confirmed IP is still 167.99.145.105. Substitute the
actual address if it changed. Use your existing SSH authentication.

```powershell
cd "C:\Users\Christopher\coding projects\team science\senior_design"
scp .run/team-science-deploy.tar.gz root@167.99.145.105:/root/
```

## 3. Load and start in the Ubuntu terminal

Run each command only after the preceding one succeeds. Extraction is for the
first deployment into this new directory.

```bash
mkdir -p /root/team-science
tar -xzf /root/team-science-deploy.tar.gz -C /root/team-science
cd /root/team-science
docker load -i images.tar
```

After Docker reports that all three images loaded, remove just the transferred
archives to recover disk space (this does not delete the installed images):

```bash
rm -- /root/team-science/images.tar /root/team-science-deploy.tar.gz
sh deploy/start-small.sh
```

The script creates a new random secret only if .env does not exist, seeds the
synthetic demo before starting the services, and preserves data in Docker volumes.
It stops the API briefly if rerun. Never share .env or run `down -v` on this server.

## 4. Verify before sharing

### Optional shared password login

Transfer `deploy/set-demo-password.py` to the same deployment directory on the
server. Run it through the existing API container, supplying `DEMO_PASSWORD`:

```bash
docker compose -f compose.small.yaml exec -T -e DEMO_PASSWORD='your-demo-password' api python - < deploy/set-demo-password.py
```

This sets the password of the existing protected `showcase@demo.invalid` user;
it refuses to modify an unmarked account. Visitors can use `/login` to open the
real dashboard and saved report. Shared access remains read-only: uploads, new
comparisons and chat are blocked; existing reports and suggestions are available.
Rerun to rotate the password. No image rebuild is needed. Existing signed-in
sessions are not revoked by a password change.

```bash
docker compose -f compose.small.yaml ps
docker compose -f compose.small.yaml logs --tail=40 proxy api
curl --fail https://spteamscience.com/health
curl -I https://www.spteamscience.com/showcase
docker stats --no-stream
free -h
df -h /
```

Check https://spteamscience.com/showcase on a phone: enter demo, expand both
comparisons and suggestions, refresh, and try a small personal upload. Repeat with
the expected number of simultaneous visitors; inspect memory, restart counts and
response times. The www address should redirect to the bare domain. This local
package has not proven live DNS/TLS or capacity on the 512 MB host.

If startup fails, send `docker compose -f compose.small.yaml ps` and the last 40
API/proxy log lines. Avoid sharing secrets. If containers restart or swap causes
long delays, reduce the demo workload or reconsider hosting capacity.

Backups, restore rehearsals and ongoing OS updates remain necessary. The general
[deployment guide](deployment.md) describes backup and release checks; use the
small Compose filename for this deployment and rebuild images locally for updates.
