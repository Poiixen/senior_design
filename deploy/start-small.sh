#!/bin/sh
# Run from the extracted deployment directory. Never replace an existing secret.
set -eu
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
    umask 077
    secret=$(openssl rand -hex 32)
    printf 'DOMAIN=spteamscience.com\nSECRET_KEY=%s\n' "$secret" > .env
fi
chmod 600 .env
docker compose -f compose.small.yaml config --quiet
# Seed before starting the other services to reduce peak memory.
docker compose -f compose.small.yaml stop api
docker compose -f compose.small.yaml run --rm --no-deps api python -m scripts.seed_showcase
docker compose -f compose.small.yaml up -d --no-build --pull never
docker compose -f compose.small.yaml ps
