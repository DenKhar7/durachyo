#!/usr/bin/env bash
# Runs on the VPS as the forced command of the CI deploy key.
# The only input is the commit SHA; anything else is rejected.
set -euo pipefail

tag="${SSH_ORIGINAL_COMMAND:-}"
if [[ ! "$tag" =~ ^[0-9a-f]{40}$ ]]; then
    echo "rejected: expected a 40-char commit sha" >&2
    exit 1
fi

cd /opt/sglypa
export TAG="$tag"
docker compose pull --quiet bot
docker compose up -d --no-build --remove-orphans bot
echo "$tag" > .deployed
docker image prune -f > /dev/null
echo "deployed $tag"
