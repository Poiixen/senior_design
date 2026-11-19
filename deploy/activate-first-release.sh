#!/usr/bin/env bash
set -euo pipefail
umask 077
release=${1:?Pass the release SHA from the GitHub run summary}
[[ "$release" =~ ^[0-9a-f]{40}$ ]] || exit 2
cd /root/team-science
incoming="$PWD/.incoming/$release"
test -f "$incoming/images.env"
test ! -f .release.env || { echo 'Already activated. Use the regular deployment workflow.'; exit 1; }
exec 9>.deployment.lock
flock -n 9 || { echo 'Another deployment is running.'; exit 1; }
backup="$PWD/backups/first-activation-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
restart_old() { docker compose -f compose.small.yaml start api; }
trap restart_old EXIT
docker compose -f compose.small.yaml stop api
docker run --rm --user 0 --entrypoint sh --mount type=volume,src=team-science_app-data,dst=/data,readonly --mount "type=bind,src=$backup,dst=/backup" caddy:2-alpine -c 'tar -czf /backup/app-data.tgz -C /data .'
docker compose --project-directory "$PWD" --env-file .env --env-file "$incoming/images.env" -f "$incoming/compose.small.yaml" run --rm --no-deps api python -m scripts.setup_shared_access
trap - EXIT
flock -u 9
bash "$incoming/deploy/apply-release.sh" "$release"
