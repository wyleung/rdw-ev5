#!/usr/bin/env bash
# Build the rdw-ev5 image and push it to GHCR, where the NAS pulls it from.
#
#   ./scripts/build-push.sh            # tag comes from pyproject.toml
#   ./scripts/build-push.sh 0.3.0rc1   # explicit override
#
# Requires a one-time login with a GitHub PAT carrying write:packages:
#   echo "$GHCR_TOKEN" | docker login ghcr.io -u wyleung --password-stdin
#
# The NAS is x86_64, so --platform is pinned rather than left to the builder's
# host arch. Pushing from an arm64 machine without it yields an image the NAS
# cannot run ("exec format error").
set -euo pipefail

IMAGE="${IMAGE:-ghcr.io/wyleung/rdw-ev5}"
PLATFORM="${PLATFORM:-linux/amd64}"

cd "$(dirname "$0")/.."

# pyproject.toml is the single source of truth for the version. An earlier
# revision of this script defaulted to `git describe --tags --always --dirty`,
# which silently produced tags like "d5bc236-dirty" on a repo with no tags —
# not a version, and impossible to correlate with a release.
version_from_pyproject() {
    python3 - <<'PY'
import tomllib
with open("pyproject.toml", "rb") as fh:
    print(tomllib.load(fh)["project"]["version"])
PY
}

TAG="${1:-$(version_from_pyproject)}"

# A dirty tree means the image contents cannot be reconstructed from any commit,
# so the tag would be a lie. Override deliberately for a throwaway test build.
if [[ -n "$(git status --porcelain)" && "${ALLOW_DIRTY:-0}" != "1" ]]; then
    echo "error: working tree is dirty — commit first, or re-run with ALLOW_DIRTY=1" >&2
    git status --short >&2
    exit 1
fi

REVISION="$(git rev-parse HEAD)"

echo "Building ${IMAGE}:${TAG} for ${PLATFORM} (revision ${REVISION:0:12})"
docker buildx build \
    --platform "${PLATFORM}" \
    --tag "${IMAGE}:${TAG}" \
    --tag "${IMAGE}:latest" \
    --label "org.opencontainers.image.version=${TAG}" \
    --label "org.opencontainers.image.revision=${REVISION}" \
    --label "org.opencontainers.image.source=https://github.com/wyleung/rdw-ev5" \
    --push \
    .

echo
echo "Pushed ${IMAGE}:${TAG}"
echo "Now point the playbook at it and deploy:"
echo "  docker_image: \"${IMAGE}:${TAG}\"   # servers/datafu-nas/rdw-ev5.yml"
