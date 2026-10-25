#!/bin/sh
# Build/test the current host architecture. No deployment and no user data volume.
# Optional first argument: an existing old image tag for size-only comparison.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker is required for image builds and comparison.' >&2
  exit 1
fi
docker info >/dev/null
if [ "$#" -gt 1 ]; then
  echo 'Usage: sh scripts/compare-images.sh [EXISTING_BASELINE_IMAGE]' >&2
  exit 1
fi
if [ "$#" -eq 1 ]; then
  docker image inspect "$1" >/dev/null
fi
# Keep both tags separate from the running Compose application's image.
docker build --pull -f Dockerfile.debian -t playpod:quickjs-debian .
docker build --pull -f Dockerfile -t playpod:quickjs-alpine .
for image in playpod:quickjs-debian playpod:quickjs-alpine; do
  echo "Runtime check: $image"
  docker run --rm -i --network none --read-only \
    --tmpfs /tmp:rw,nosuid,nodev,size=256m,mode=1777 \
    --entrypoint python "$image" - < scripts/smoke_image.py
done
mkdir -p build
report=build/image-sizes.tsv
printf 'image\tarchitecture\tbytes\n' > "$report"
for image in ${1:+"$1"} playpod:quickjs-debian playpod:quickjs-alpine; do
  docker image inspect --format '{{printf "%s\t%s\t%d" (index .RepoTags 0) .Architecture .Size}}' "$image" >> "$report"
done
cat "$report"
awk -F '\t' 'NR == 1 { next } { printf "%s (%s): %.1f MiB\n", $1, $2, $3 / 1048576 }' "$report"
echo 'Sizes are local uncompressed Docker image bytes, not registry download sizes.'
echo 'Report: build/image-sizes.tsv'
