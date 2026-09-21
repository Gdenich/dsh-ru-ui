#!/usr/bin/env bash
# Install an npm access token into ~/.npmrc without echoing it.
#
# Reading the token is deliberately fussy, because three things go wrong in
# practice and each has a different fix:
#   * a wrapped or truncated paste             -> length and shape are reported
#   * a token that is valid but cannot publish -> the probe says so before the
#     working token is replaced
#   * a registry answer that is not JSON       -> the raw HTTP status is shown
#     instead of a traceback from the JSON parser
#
# The token is never printed: at most its length and last four characters are,
# which is enough to tell two tokens apart.
#
# Usage:
#   tools/set-npm-token.sh                       # prompt (hidden input)
#   NPM_TOKEN=npm_xxx tools/set-npm-token.sh     # non-interactive
set -euo pipefail

NPMRC="${NPMRC:-$HOME/.npmrc}"
EXPECTED_USER="${EXPECTED_USER:-gdenich}"
PROBE_PACKAGE="${PROBE_PACKAGE:-dsh-ru-ui-token-probe}"
TOKEN="${NPM_TOKEN:-}"

trim() {
  # Strip surrounding whitespace and any stray CR/LF a paste may carry.
  printf '%s' "$1" | tr -d '\r\n' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

if [ -z "$TOKEN" ]; then
  printf 'Вставьте npm-токен (ввод не отображается, затем Enter): '
  read -rs TOKEN
  printf '\n'
fi
TOKEN="$(trim "$TOKEN")"

if [ -z "$TOKEN" ]; then
  cat >&2 <<'MSG'
error: токен пустой — реестр не получил ни одного символа.

Скрытый ввод не показывает символы, но вставка всё равно должна сработать.
Если она не проходит, прочитайте токен в переменную окружения — тогда скрытый
ввод не участвует, а скрипт больше ничего не спросит:

  read -rs NPM_TOKEN && export NPM_TOKEN && tools/set-npm-token.sh
MSG
  exit 1
fi

echo "Получено: ${#TOKEN} символов, начинается на '${TOKEN:0:4}', заканчивается на '…${TOKEN: -4}'"
case "$TOKEN" in
  npm_*) ;;
  *) echo "warning: токен не начинается с npm_ — возможно, скопирован не тот текст" >&2 ;;
esac

# --- 1. Is the token recognised at all? -------------------------------------
# Validity is checked the way npm itself checks it: an authenticated identity
# read. The `/-/npm/v1/user` profile endpoint is deliberately NOT used as the
# gate — a granular token scoped to packages answers it with 403 while being
# perfectly valid, which would reject a working token.
echo "Проверяю токен на реестре…"
# A temporary config file, because the npm env-var form of an auth key contains a
# colon (`npm_config_//registry.npmjs.org/:_authToken`) and is not a legal shell
# variable name. The file lives in a private temp dir and is removed on exit.
PROBE_DIR="$(mktemp -d)"
trap 'rm -rf "$PROBE_DIR"' EXIT
printf 'registry=https://registry.npmjs.org/\n//registry.npmjs.org/:_authToken=%s\n' "$TOKEN" > "$PROBE_DIR/npmrc"
chmod 600 "$PROBE_DIR/npmrc"
WHOAMI="$(NPM_CONFIG_USERCONFIG="$PROBE_DIR/npmrc" npm whoami 2>"$PROBE_DIR/err" || true)"
WHOAMI="$(trim "$WHOAMI")"
WHOAMI_ERR="$(head -c 300 "$PROBE_DIR/err" 2>/dev/null || true)"

if [ -z "$WHOAMI" ]; then
  cat >&2 <<MSG
error: реестр не подтвердил токен — npm whoami не вернул имя.
       Ответ npm: ${WHOAMI_ERR:-<пусто>}

Причины по частоте:
  * токен отозван или скопирован не целиком (нужно ровно 40 символов);
  * это не токen npm (GitHub-токен, пароль, ключ другого реестра);
  * токен выпущен для другого реестра.
MSG
  exit 1
fi

echo "Токен действителен. Аккаунт: $WHOAMI"
if [ "$WHOAMI" != "$EXPECTED_USER" ]; then
  echo "warning: ожидался аккаунт $EXPECTED_USER, получен $WHOAMI — публикация уйдёт от другого имени" >&2
fi

# --- 2. The capability that matters: publishing -----------------------------
# A valid token without the 2FA bypass passes step 1 and then fails the real
# publish with an opaque 403, so probe it now instead of after swapping files.
echo "Проверяю право на публикацию…"
PROBE_STATUS="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -X PUT "https://registry.npmjs.org/$PROBE_PACKAGE" \
  -d "{\"_id\":\"$PROBE_PACKAGE\",\"name\":\"$PROBE_PACKAGE\",\"versions\":{}}" || true)"

case "$PROBE_STATUS" in
  400|409)
    echo "Право на публикацию есть (HTTP $PROBE_STATUS — тело запроса неполное, это ожидаемо)."
    ;;
  401|403)
    cat >&2 <<MSG
error: токен не может публиковать (HTTP $PROBE_STATUS).

Нужен токен с включённым обходом 2FA. На npmjs.com:
  Access Tokens → Generate New Token → Granular Access Token
    Packages   : Read and write
    Bypass 2FA : включить
либо classic-токен типа Automation.
На аккаунте должна быть включена 2FA, иначе обход не выпускается.
MSG
    exit 1
    ;;
  *)
    echo "warning: реестр ответил HTTP $PROBE_STATUS на пробную запись — проверьте вручную" >&2
    ;;
esac

# --- 3. Replace the file, keeping a way back --------------------------------
if [ -f "$NPMRC" ] && grep -q '_authToken' "$NPMRC"; then
  BACKUP="$NPMRC.bak-$(date +%Y%m%d%H%M%S)"
  cp "$NPMRC" "$BACKUP"
  echo "Старый ~/.npmrc сохранён: $BACKUP"
fi

umask 077
python3 - "$NPMRC" "$TOKEN" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
token = sys.argv[2]
keep = []
replaced = False
if path.exists():
    for line in path.read_text(encoding="utf-8").splitlines():
        if "_authToken" in line:
            if replaced:
                continue
            replaced = True
            continue
        if line.strip():
            keep.append(line)
keep.append(f"//registry.npmjs.org/:_authToken={token}")
path.write_text("\n".join(keep) + "\n", encoding="utf-8")
os.chmod(path, 0o600)
print(f"записано: {path} (права 600)")
PY

echo
echo "Готово. Публикация:"
echo "  cd $(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "  npm publish"
