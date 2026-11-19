#!/usr/bin/env bash
# Run on the Droplet after CI transfers images and configuration.
set -Eeuo pipefail
umask 077
release=${1:?Pass the full release commit SHA}
[[ "$release" =~ ^[0-9a-f]{40}$ ]] || exit 2
cd /root/team-science
exec 9>.deployment.lock
flock -n 9 || { echo 'Another deployment is running.'; exit 1; }
incoming="$PWD/.incoming/$release"
test -f .env
test -f "$incoming/images.env"
test -f "$incoming/compose.small.yaml"
test -f "$incoming/deploy/Caddyfile"
docker image inspect "team-science-api:$release" "team-science-frontend:$release" >/dev/null

# Snapshot the actual running image IDs, including the legacy showcase release.
api_id=$(docker inspect --format '{{.Image}}' team-science-api-1)
frontend_id=$(docker inspect --format '{{.Image}}' team-science-frontend-1)
backup="$PWD/backups/$(date -u +%Y%m%dT%H%M%SZ)-$release"
mkdir -p "$backup/deploy"
cp compose.small.yaml "$backup/compose.small.yaml"
cp deploy/Caddyfile "$backup/deploy/Caddyfile"
if [ -f .release.env ]; then cp .release.env "$backup/release.env"; fi
docker tag "$api_id" team-science-api:rollback
docker tag "$frontend_id" team-science-frontend:rollback
printf 'API_IMAGE=team-science-api:rollback\nFRONTEND_IMAGE=team-science-frontend:rollback\n' > "$backup/rollback.env"

current() {
  if [ -f .release.env ]; then
    docker compose --env-file .env --env-file .release.env -f compose.small.yaml "$@"
  else
    docker compose --env-file .env -f compose.small.yaml "$@"
  fi
}
rollback() {
  trap - ERR
  echo 'Deployment failed; restoring previous application images and configuration.'
  cp "$backup/compose.small.yaml" compose.small.yaml
  cp "$backup/deploy/Caddyfile" deploy/Caddyfile
  if [ -f "$backup/release.env" ]; then cp "$backup/release.env" .release.env; else rm -f .release.env; fi
  # Legacy configurations have fixed showcase tags; restore those too.
  docker tag "$api_id" team-science-api:showcase
  docker tag "$frontend_id" team-science-frontend:showcase
  current up -d --no-build --pull never --force-recreate --wait --wait-timeout 180 || true
  echo "Data backup retained at $backup/app-data.tgz. Database is not automatically rewound."
  exit 1
}
trap rollback ERR
current stop api
# Back up SQLite and Parquet together while no application writer is running.
docker run --rm --user 0 --entrypoint sh --mount type=volume,src=team-science_app-data,dst=/data,readonly --mount "type=bind,src=$backup,dst=/backup" caddy:2-alpine -c 'tar -czf /backup/app-data.tgz -C /data .'

# Refuse a shared-mode rollout without both identities. Passwords are never printed.
docker compose --project-directory "$PWD" --env-file .env --env-file "$incoming/images.env" -f "$incoming/compose.small.yaml" run --rm --no-deps api python -c 'import os; from sqlalchemy import select; from backend.database.connection import create_sqlite_engine, session_scope; from backend.models import User; from backend.services.showcase import EMAIL, is_demo_user; engine=create_sqlite_engine(os.environ["DATABASE_PATH"]); session_check=session_scope(engine); session=session_check.__enter__(); users={u.email:u for u in session.scalars(select(User)).all()}; assert os.getenv("AUTH_MODE", "shared") == "verified" or ("admin@teamscience.invalid" in users and EMAIL in users and is_demo_user(engine, users[EMAIL].id)), "Run scripts.setup_shared_access before deploying shared access"; session_check.__exit__(None,None,None)'

cp "$incoming/compose.small.yaml" compose.small.yaml
cp "$incoming/deploy/Caddyfile" deploy/Caddyfile
cp "$incoming/images.env" .release.env
current config --quiet
current up -d --no-build --pull never --force-recreate --wait --wait-timeout 180
# Check the public HTTPS route and authentication page as well as API health.
domain=$(current exec -T proxy printenv DOMAIN)
curl --fail --silent --show-error --retry 8 --retry-all-errors --retry-delay 3 "https://$domain/health" >/dev/null
curl --fail --silent --show-error --retry 8 --retry-all-errors --retry-delay 3 "https://$domain/login" >/dev/null
trap - ERR
printf '%s\n' "$release" > .deployed-commit
echo "Deployed $release successfully. Backup: $backup"
# Keep current and rollback image layers; discard older commit tags for this app.
while read -r repository tag; do
  if [[ "$repository" =~ ^team-science-(api|frontend)$ ]] && [[ "$tag" =~ ^[0-9a-f]{40}$ ]] && [ "$tag" != "$release" ]; then
    docker image rm "$repository:$tag" || true
  fi
done < <(docker image ls --format '{{.Repository}} {{.Tag}}')
# Keep three local data backups. Copy backups off-server for disaster recovery.
find "$PWD/backups" -mindepth 2 -maxdepth 2 -name app-data.tgz -printf '%T@ %p\n' | sort -nr | tail -n +4 | cut -d' ' -f2- | while IFS= read -r archive; do rm -- "$archive"; done
