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
echo "Проверяю токен на реестре…"
USER_RESPONSE="$(curl -s -w '\n%{http_code}' -H "Authorization: Bearer $TOKEN" \
  https://registry.npmjs.org/-/npm/v1/user || true)"
USER_STATUS="$(printf '%s' "$USER_RESPONSE" | tail -n1)"
USER_BODY="$(printf '%s' "$USER_RESPONSE" | sed '$d')"

if [ "$USER_STATUS" != "200" ]; then
  cat >&2 <<MSG
error: реестр отклонил токен (HTTP $USER_STATUS).
       Ответ реестра: $(printf '%s' "$USER_BODY" | head -c 300)

Что это значит:
  * 401 — токен недействителен: отозван, скопирован не целиком, либо это не токен;
  * 403 — токен распознан, но прав не хватает.

Токены npm имеют вид npm_ + 36 символов, всего 40. Если длина выше другая —
вставка оборвалась, повторите.
MSG
  exit 1
fi

WHOAMI="$(printf '%s' "$USER_BODY" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("name",""))' 2>/dev/null || true)"
TFA="$(printf '%s' "$USER_BODY" | python3 -c 'import json,sys;print(json.dumps(json.load(sys.stdin).get("tfa")))' 2>/dev/null || echo '?')"

echo "Токен действителен. Аккаунт: ${WHOAMI:-?}, 2FA на аккаунте: $TFA"
if [ -n "$WHOAMI" ] && [ "$WHOAMI" != "$EXPECTED_USER" ]; then
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
На аккаунте должна быть включена 2FA — сейчас реестр сообщает tfa: $TFA.
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
