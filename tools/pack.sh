#!/usr/bin/env bash
# Build a distributable copy of the plugin.
#
# The runtime needs only four files: the host half, the browser bundle, the
# loader patch and the manifest. tools/ and test/ exist to rebuild and verify
# the dictionary and are useless on a target machine that will not have the DSH
# source bundles to re-extract from — so the release archive carries the built
# artifact, not the workshop.
#
# Usage:
#   tools/pack.sh [output-dir]        # default: dist/
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$PLUGIN_DIR/dist}"
NAME="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['name'])" "$PLUGIN_DIR/package.json")"
VERSION="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" "$PLUGIN_DIR/package.json")"
STAGE="$OUT_DIR/$NAME"
ARCHIVE="$OUT_DIR/$NAME-$VERSION.tar.gz"

rm -rf "$STAGE" "$ARCHIVE"
mkdir -p "$STAGE/lib"

cp "$PLUGIN_DIR/package.json" "$PLUGIN_DIR/cordis.patch.yml" "$PLUGIN_DIR/README.md" "$PLUGIN_DIR/LICENSE" "$STAGE/"
cp "$PLUGIN_DIR/lib/index.js" "$PLUGIN_DIR/lib/client.js" "$STAGE/lib/"

# `files` in the manifest must match what actually ships.
python3 - "$STAGE" <<'PY'
import json
import os
import sys

stage = sys.argv[1]
manifest = json.load(open(os.path.join(stage, "package.json"), encoding="utf-8"))
declared = set(manifest.get("files", []))
present = {
    os.path.relpath(os.path.join(root, name), stage)
    for root, _, names in os.walk(stage)
    for name in names
}
missing = {entry for entry in declared if not any(p == entry or p.startswith(entry + "/") for p in present)}
if missing:
    raise SystemExit(f"package.json files[] declares missing entries: {sorted(missing)}")
print(f"payload verified against files[]: {len(present)} files")
PY

tar -czf "$ARCHIVE" -C "$OUT_DIR" "$NAME"
du -h "$ARCHIVE" | awk '{print "archive: " $1}'
echo "$ARCHIVE"
