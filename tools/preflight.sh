#!/usr/bin/env bash
# Preflight for publishing a DSH plugin to npm and GitHub.
#
# Checks the things that actually blocked a real release, in the order they fail:
#   1. the manifest will produce a working DSH plugin (bundle patch + client face)
#   2. everything `files[]` promises exists on disk
#   3. the npm token authenticates AND can publish (a token without the 2FA
#      bypass is valid and still gets a 403 on publish — the most confusing
#      failure in the whole flow)
#   4. the package name is free, or the version is not already published
#   5. the repository exists and the release tag is annotated
#
# Read-only: it publishes nothing and changes nothing outside a temp dir.
#
# Usage:
#   tools/preflight.sh [project-dir] [github-owner/repo]
#   tools/preflight.sh . Gdenich/other-plugin
set -uo pipefail

PROJECT_DIR="$(cd "${1:-.}" && pwd)"
REPO="${2:-}"
FAILED=0
NOTE=0

say()  { printf '%s\n' "$*"; }
ok()   { printf '  OK    %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; FAILED=$((FAILED + 1)); }
warn() { printf '  WARN  %s\n' "$*"; NOTE=$((NOTE + 1)); }

MANIFEST="$PROJECT_DIR/package.json"
if [ ! -f "$MANIFEST" ]; then
  say "error: no package.json in $PROJECT_DIR"
  exit 2
fi

json() { python3 -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1])).get(sys.argv[2],''),ensure_ascii=False) if False else '')" "$MANIFEST" "$1" 2>/dev/null; }

NAME="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('name',''))" "$MANIFEST")"
VERSION="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('version',''))" "$MANIFEST")"
say "publishing check: $NAME@$VERSION"
say "project: $PROJECT_DIR"
say ""

# --- 1. Will DSH load this at all? -----------------------------------------
say "1. DSH plugin face"
PATCH="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print((d.get('dsh') or {}).get('bundle',{}).get('patch',''))" "$MANIFEST")"
if [ -z "$PATCH" ]; then
  bad "dsh.bundle.patch is missing — 'dsh plugin add' will install it as a plain dependency and never load it"
elif [ ! -f "$PROJECT_DIR/$PATCH" ]; then
  bad "dsh.bundle.patch points at $PATCH, which does not exist"
else
  ok "dsh.bundle.patch -> $PATCH"
  if ! grep -q "insert:" "$PROJECT_DIR/$PATCH" 2>/dev/null; then
    warn "$PATCH has no 'insert:' entry — check it actually adds the plugin row"
  fi
  ID="$(python3 -c "
import re,sys
t=open(sys.argv[1],encoding='utf-8').read()
m=re.search(r'-\s*insert:\s*\n\s*-\s*id:\s*(\S+)', t)
print(m.group(1) if m else '')
" "$PROJECT_DIR/$PATCH")"
  [ -n "$ID" ] && ok "loader row id: $ID"
fi

PLATFORM="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print((d.get('dsh') or {}).get('client',{}).get('platform',''))" "$MANIFEST")"
if [ -n "$PLATFORM" ]; then
  say "   client plugin (platform: $PLATFORM)"
  CLIENT_REL="$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
e=(d.get('exports') or {}).get('./client')
if isinstance(e,str): print(e)
elif isinstance(e,dict): print(e.get('default',''))
" "$MANIFEST")"
  if [ -z "$CLIENT_REL" ]; then
    bad "dsh.client is declared but exports['./client'] does not resolve to a file"
  elif [ ! -f "$PROJECT_DIR/$CLIENT_REL" ]; then
    bad "exports['./client'] -> $CLIENT_REL is missing. Client bundles are served as committed artifacts (the real loader has no bundler); run the build"
  else
    ok "client bundle present: $CLIENT_REL ($(wc -c < "$PROJECT_DIR/$CLIENT_REL" | tr -d ' ') bytes)"
    if grep -q "__DICTIONARY__\|__PLACEHOLDER__" "$PROJECT_DIR/$CLIENT_REL" 2>/dev/null; then
      bad "the client bundle still contains a template placeholder — the build did not run"
    fi
    if ! grep -q "__ModuleLoader__" "$PROJECT_DIR/$CLIENT_REL" 2>/dev/null; then
      warn "client bundle never calls window.__ModuleLoader__.load — is it really a DSH client bundle?"
    fi
  fi
  INJECT="$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(' '.join((d.get('dsh') or {}).get('client',{}).get('inject',[])))" "$MANIFEST")"
  [ -n "$INJECT" ] && ok "dsh.client.inject: $INJECT"
  say "   note: every external the bundle requires must be listed in inject;"
  say "         a relative require() cannot work (the loader resolves only those names)"
else
  say "   host-only plugin (no dsh.client) — fine for a tool/provider plugin"
fi
say ""

# --- 2. Does files[] match reality? ----------------------------------------
say "2. Tarball contents"
FILES="$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))
print('\n'.join(d.get('files') or []))
" "$MANIFEST")"
if [ -z "$FILES" ]; then
  warn "no files[] field — npm will pack the whole directory (tests, sources, vendor)"
else
  while IFS= read -r entry; do
    [ -z "$entry" ] && continue
    if [ -e "$PROJECT_DIR/$entry" ]; then ok "files[]: $entry"
    else bad "files[] lists $entry, which does not exist"; fi
  done <<< "$FILES"
fi
for must in README.md LICENSE; do
  if [ -f "$PROJECT_DIR/$must" ]; then ok "$must present"
  else warn "$must missing — npm wants it and the repo page looks bare without it"; fi
done
say ""

# --- 3. Can this token publish? --------------------------------------------
say "3. npm credentials"
TOKEN="$(python3 -c "
import os
p=os.path.expanduser('~/.npmrc')
print(open(p,encoding='utf-8').read().split('_authToken=')[1].split()[0] if '_authToken=' in open(p,encoding='utf-8').read() else '')
" 2>/dev/null)"
if [ -z "$TOKEN" ]; then
  warn "no token in ~/.npmrc — run tools/set-npm-token.sh before publishing"
else
  TMPD="$(mktemp -d)"; trap 'rm -rf "$TMPD"' EXIT
  printf 'registry=https://registry.npmjs.org/\n//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$TMPD/npmrc"
  chmod 600 "$TMPD/npmrc"
  WHOAMI="$(NPM_CONFIG_USERCONFIG="$TMPD/npmrc" npm whoami 2>/dev/null || true)"
  if [ -n "$WHOAMI" ]; then
    ok "token authenticates as $WHOAMI"
    # The probe targets a throwaway name, so the registry's answer is read, not
    # just its status: npm rejects an unauthorized write with a bare numeric
    # error, while an authorized write that fails content checks (spam
    # detection, bad body) returns a JSON error explaining itself.
    PROBE_BODY="$(mktemp)"
    PROBE="$(curl -s -o "$PROBE_BODY" -w '%{http_code}' \
      -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
      -X PUT "https://registry.npmjs.org/preflight-probe-$(date +%s)" \
      -d '{"_id":"probe","name":"probe","versions":{}}')"
    PROBE_ERROR="$(python3 -c "
import json,sys
try:
    print(json.load(open(sys.argv[1], encoding='utf-8')).get('error',''))
except Exception:
    print('')
" "$PROBE_BODY" 2>/dev/null)"
    rm -f "$PROBE_BODY"
    case "$PROBE" in
      400|409) ok "token can publish (probe HTTP $PROBE)" ;;
      403)
        case "$PROBE_ERROR" in
          *"Two-factor"*|*"2fa"*|*"2FA"*|"")
            bad "token authenticates but cannot publish (HTTP 403). Need Bypass 2FA on the token and 2FA on the account" ;;
          *)
            ok "token can publish (HTTP 403 was a content rejection, not auth): $PROBE_ERROR" ;;
        esac ;;
      401) bad "token was not accepted for a write (HTTP 401)" ;;
      *) warn "publish probe answered HTTP $PROBE ${PROBE_ERROR:+— $PROBE_ERROR}" ;;
    esac
  else
    bad "token in ~/.npmrc does not authenticate (npm whoami returned nothing)"
  fi
fi
say ""

# --- 4. Name and version availability --------------------------------------
say "4. Registry state"
if npm view "$NAME" version >/dev/null 2>&1; then
  PUBLISHED="$(npm view "$NAME" version 2>/dev/null)"
  if [ "$PUBLISHED" = "$VERSION" ]; then
    warn "$NAME@$VERSION is already published — bump the version before releasing"
  else
    ok "$NAME exists, latest is $PUBLISHED; $VERSION is free to publish"
    MAINTAINER="$(npm view "$NAME" maintainers 2>/dev/null | head -1)"
    warn "confirm you maintain $NAME ($MAINTAINER) — do not republish someone else's package"
  fi
else
  ok "$NAME is free in the registry"
fi
say ""

# --- 5. GitHub side ---------------------------------------------------------
say "5. GitHub"
if [ -n "$REPO" ]; then
  if gh repo view "$REPO" --json name,visibility >/dev/null 2>&1; then
    VIS="$(gh repo view "$REPO" --json visibility --jq .visibility)"
    ok "$REPO exists ($VIS)"
  else
    bad "$REPO not found — create it with: gh repo create ${REPO#*/} --public --source=. --remote=origin --push"
  fi
fi
if [ -d "$PROJECT_DIR/.git" ]; then
  ok "git repository present"
  if git -C "$PROJECT_DIR" tag -l | grep -q .; then
    LAST="$(git -C "$PROJECT_DIR" describe --tags --abbrev=0 2>/dev/null || echo '')"
    TYPE="$(git -C "$PROJECT_DIR" cat-file -t "$LAST" 2>/dev/null || echo '')"
    if [ "$TYPE" = "tag" ]; then ok "latest tag $LAST is annotated (worth pushing)"
    else warn "latest tag $LAST is LIGHTWEIGHT — 'git push --follow-tags' will skip it and no workflow will run. Use: npm version patch -m \"Release %s\""; fi
  fi
  if ! grep -q "^node_modules/\|^dist/" "$PROJECT_DIR/.gitignore" 2>/dev/null; then
    warn ".gitignore does not exclude node_modules/ or dist/ — check what is about to be committed"
  fi
  if git -C "$PROJECT_DIR" check-ignore -q . 2>/dev/null; then :; fi
  for tmp in "$PROJECT_DIR/build" "$PROJECT_DIR/dist"; do
    [ -d "$tmp" ] && say "   note: $(basename "$tmp")/ is present; make sure CI does not depend on it if it is gitignored"
  done
else
  warn "no git repository here — 'gh repo create --source=.' needs one"
fi
say ""

# --- verdict ----------------------------------------------------------------
if [ "$FAILED" -gt 0 ]; then
  say "FAILED: $FAILED blocking issue(s), $NOTE warning(s)"
  exit 1
fi
say "PASSED with $NOTE warning(s). Publish with:  npm publish   (or push an annotated tag to let CI do it)"
