#!/usr/bin/env bash
set -euo pipefail

# Generates a small disposable MD5 rainbow table in a new local directory.
# This is a CPU/disk-writing operation; run manually, never from an unattended QA batch.
command -v rtgen >/dev/null || { echo "rtgen is not installed" >&2; exit 1; }
command -v rtsort >/dev/null || { echo "rtsort is not installed" >&2; exit 1; }
OUT="${1:-$(pwd)/rtsort-fixture-output}"
mkdir -p "$OUT"
chmod 700 "$OUT"
cd "$OUT"
# Tiny parameters: MD5, lowercase, plaintext lengths 1-2, 20 chains x 20 links.
rtgen md5 loweralpha 1 2 0 20 20 0
# Sorting modifies the generated table in place.
rtsort .
printf 'Disposable table generated in: %s\n' "$OUT"
