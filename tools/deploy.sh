#!/usr/bin/env bash
# Deploy dsh-ru-ui into a DSH profile.
#
# A DSH profile is an ordinary package directory: a plugin is a dependency whose
# package declares `dsh.bundle.patch` and `dsh.client`, plus one entry in
# `dsh.profile.bundles`. This script performs exactly that, idempotently, and
# backs the manifest up before touching it.
#
# The Desktop profile is managed by the Electron app, so its manifest is edited
# directly here rather than through `dsh plugin` (the CLI refuses that profile:
# "managed exclusively by the Electron application"). Appending to the bundle
# list also stops the app from normalising the manifest, because a list that no
# longer matches the shipped template is treated as user-owned.
#
# Usage:
#   tools/deploy.sh [profile-name]        # default: desktop
#   DSH_HOME=/path tools/deploy.sh web
set -euo pipefail

PROFILE="${1:-desktop}"
PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DSH_HOME="${DSH_HOME:-$HOME/.dsh}"
PROFILE_DIR="$DSH_HOME/profiles/$PROFILE"
PACKAGE_NAME="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['name'])" "$PLUGIN_DIR/package.json")"

if [ ! -d "$PROFILE_DIR" ]; then
  echo "error: profile not found: $PROFILE_DIR" >&2
  exit 1
fi

echo "plugin:  $PACKAGE_NAME"
echo "source:  $PLUGIN_DIR"
echo "profile: $PROFILE_DIR"

# 1. Make the package resolvable from the profile.
mkdir -p "$PROFILE_DIR/node_modules"
LINK="$PROFILE_DIR/node_modules/$PACKAGE_NAME"
if [ -L "$LINK" ] || [ -e "$LINK" ]; then
  rm -rf "$LINK"
fi
ln -s "$PLUGIN_DIR" "$LINK"
echo "linked:  $LINK -> $PLUGIN_DIR"

# 2. Register the dependency and its bundle patch layer.
PROFILE_DIR="$PROFILE_DIR" PLUGIN_DIR="$PLUGIN_DIR" PACKAGE_NAME="$PACKAGE_NAME" python3 - <<'PY'
import json
import os
import shutil

profile_dir = os.environ["PROFILE_DIR"]
plugin_dir = os.environ["PLUGIN_DIR"]
name = os.environ["PACKAGE_NAME"]
manifest_path = os.path.join(profile_dir, "package.json")

shutil.copy2(manifest_path, manifest_path + ".bak-" + name)
with open(manifest_path, encoding="utf-8") as fh:
    manifest = json.load(fh)

manifest.setdefault("dependencies", {})[name] = f"link:{plugin_dir}"
bundles = manifest.setdefault("dsh", {}).setdefault("profile", {}).setdefault("bundles", [])
if name not in bundles:
    bundles.append(name)

with open(manifest_path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

print(f"manifest: dependency link:{plugin_dir}")
print(f"manifest: bundles now {len(bundles)} entries, {name} at the end")
PY

echo
echo "Restart DSH to load the plugin: the bundle list is read at profile boot."
echo "Reload the window afterwards; the interface switches to Russian on first run."
