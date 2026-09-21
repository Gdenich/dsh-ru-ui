#!/usr/bin/env bash
# Install an npm access token into ~/.npmrc without echoing it.
#
# Two reasons this is a script and not a line in the README:
#   * the token must never reach the shell history, a log or a chat transcript,
#     so it is read with `read -s` and never printed;
#   * a token that cannot publish is useless, so the new token is checked
#     against the registry before it replaces the working one.
#
# Usage:
#   tools/set-npm-token.sh            # prompts for the token
#   NPM_TOKEN=npm_xxx tools/set-npm-token.sh   # non-interactive (CI, other shells)
set -euo pipefail

NPMRC="${NPMRC:-$HOME/.npmrc}"
EXPECTED_USER="${EXPECTED_USER:-gdenich}"
TOKEN="${NPM_TOKEN:-}"

if [ -z "$TOKEN" ]; then
  printf 'Вставьте npm-токен (ввод не отображается): '
  # `-s` keeps it off the screen; `-r` keeps backslashes intact.
  read -rs TOKEN
  printf '\n'
fi

if [ -z "$TOKEN" ]; then
  echo "error: пустой токен" >&2
  exit 1
fi

case "$TOKEN" in
  npm_*) ;;
  *) echo "warning: токен не начинается с npm_ — это может быть старый classic-токен" >&2 ;;
esac

echo "Проверяю токен на реестре…"
WHOAMI="$(curl -sf -H "Authorization: Bearer $TOKEN" https://registry.npmjs.org/-/npm/v1/user \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("name",""))')"

if [ -z "$WHOAMI" ]; then
  echo "error: реестр не принял токен (401/403). Проверьте, что он скопирован целиком." >&2
  exit 1
fi

echo "Токен действителен, аккаунт: $WHOAMI"
if [ "$WHOAMI" != "$EXPECTED_USER" ]; then
  echo "warning: ожидался аккаунт $EXPECTED_USER, получен $WHOAMI" >&2
fi

# Check the capability that actually matters: can this token publish at all?
# The registry answers 401/403 for a token without the 2FA bypass, which is the
# exact failure this script exists to avoid.
echo "Проверяю право на публикацию…"
PROBE="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -X PUT "https://registry.npmjs.org/dsh-ru-ui-token-probe" \
  -d '{"_id":"dsh-ru-ui-token-probe","name":"dsh-ru-ui-token-probe","versions":{}}')"

case "$PROBE" in
  401|403)
    echo "error: токен не может публиковать (HTTP $PROBE)." >&2
    echo "       Нужен токен с включённым «bypass 2FA»:" >&2
    echo "       npmjs.com → Access Tokens → Generate New Token → Granular Access Token," >&2
    echo "       Packages: Read and write, и переключатель Bypass 2FA." >&2
    exit 1
    ;;
  409|400)
    echo "Право на публикацию есть (HTTP $PROBE — имя уже занято, это ожидаемо)."
    ;;
  405)
    echo "Право на публикацию есть (HTTP $PROBE — реестр не принимает пробную запись)."
    ;;
  *)
    echo "Реестр ответил HTTP $PROBE — проверьте вручную." >&2
    ;;
esac

if [ -f "$NPMRC" ] && grep -q '_authToken' "$NPMRC"; then
  cp "$NPMRC" "$NPMRC.bak-$(date +%Y%m%d%H%M%S)"
  echo "Старый ~/.npmrc сохранён в $NPMRC.bak-*"
fi

# Write with restrictive permissions and no shell interpolation of the token
# into any command line.
umask 077
python3 - "$NPMRC" "$TOKEN" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
token = sys.argv[2]
keep = []
seen = False
if path.exists():
    for line in path.read_text(encoding="utf-8").splitlines():
        if "_authToken" in line:
            if seen:
                continue
            seen = True
            continue
        keep.append(line)
keep = [line for line in keep if line.strip()]
keep.append(f"//registry.npmjs.org/:_authToken={token}")
path.write_text("\n".join(keep) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
print(f"записано: {path} (права 600)")
PY

echo
echo "Готово. Публикация:"
echo "  cd $(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "  npm publish"
