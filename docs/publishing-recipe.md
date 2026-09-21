# Рецепт: публикация плагина DSH в npm и GitHub

Проверенный порядок действий. Собран по реальному релизу `dsh-ru-ui`, включая
четыре падения, которые пришлось разбирать. Копируется в любой workspace.

---

## 0. Что должно быть в пакете

DSH-плагин — обычный npm-пакет с двумя полями в `package.json`:

```json
{
  "name": "my-dsh-plugin",
  "version": "0.1.0",
  "type": "module",
  "main": "lib/index.js",
  "exports": {
    ".": { "default": "./lib/index.js" },
    "./client": "./lib/client.js",
    "./cordis.patch.yml": "./cordis.patch.yml",
    "./package.json": "./package.json"
  },
  "files": ["lib/index.js", "lib/client.js", "cordis.patch.yml", "README.md", "LICENSE"],
  "dsh": {
    "bundle": { "patch": "./cordis.patch.yml" },
    "client": {
      "platform": "web",
      "inject": ["@deepseek-ai/dsh-client-locale"]
    }
  }
}
```

* **`dsh.bundle.patch`** — обязателен. По нему `dsh plugin add` понимает, что
  зависимость является слоем профиля, и дописывает её в `dsh.profile.bundles`
  сам. Без этого поля пакет поставится как обычная библиотека и не загрузится
  (CLI напишет предупреждение `declares no dsh.bundle`).
* **`dsh.client`** — только для плагинов с браузерной половиной. `platform`
  всегда `web`, а `inject` перечисляет **все** пакеты, которые бандл требует.
* **`files[]`** — ограничивает поставку. Без него npm упакует весь каталог
  вместе с тестами и исходниками переводов.

`cordis.patch.yml` добавляет строку в дерево загрузчика:

```yaml
- insert:
    - id: my-dsh-plugin      # должен совпадать с id в бандле и с module.exports.name
      name: my-dsh-plugin
```

### Две ловушки сборки

1. **Браузерный бандл обязан быть собран заранее и лежать в репозитории.**
   Загрузчик клиентских модулей DSH не собирает ничего на месте, а `require`
   внутри бандла резолвит **только** имена из `dsh.client.inject` — относительный
   `require('./dict.js')` не сработает. Всё, что нужно бандлу, вшивается на сборке.
2. **Хост-половина может быть пустой.** Если весь плагин живёт в браузере,
   `lib/index.js` достаточно свести к `export const name = '...'`, чтобы
   загрузчик увидел строку. Тогда у плагина нет ни настроек, ни маршрутов, ни
   состояния на хосте.

---

## 1. Предполётная проверка

Скрипт `tools/preflight.sh` из репозитория `dsh-ru-ui` проверяет всё, что ломало
релиз, и ничего не публикует:

```bash
tools/preflight.sh . Gdenich/my-dsh-plugin
```

Что он смотрит: манифест как DSH-плагин, наличие всех файлов из `files[]`,
работоспособность npm-токена **с проверкой права на публикацию**, свободна ли
версия, есть ли аннотированный тег и репозиторий.

---

## 2. npm: доступ

Публикация требует одновременно:

* **2FA, включённая на аккаунте** — без неё обход не выпускается;
* **токен с включённым «Bypass 2FA»** — Granular Access Token с правами
  `Packages: Read and write`, либо classic-токен типа *Automation*.

Токен кладётся в `~/.npmrc` (права `600`):

```
//registry.npmjs.org/:_authToken=npm_xxxxxxxx
```

Безопаснее — скриптом, который читает токен скрытым вводом и не подменяет
рабочий файл, если токен не умеет публиковать:

```bash
read -rs NPM_TOKEN && export NPM_TOKEN && tools/set-npm-token.sh
```

Если скрытый ввод не принимает вставку (частая беда), передайте токен через
файл: `printf '%s' 'ТОКЕН' > /tmp/npmtok && chmod 600 /tmp/npmtok`, затем
`NPM_TOKEN="$(cat /tmp/npmtok)" tools/set-npm-token.sh`, затем удалите файл.

### Как понять, что токен годный

Валидность проверяется `npm whoami`. **Не** используйте для этого эндпоинт
`/-/npm/v1/user`: granular-токен, ограниченный пакетами, отвечает на него `403`
при полностью живом токене.

Право на публикацию — отдельная проверка, и её ответ надо читать целиком:

```bash
curl -s -w '\nHTTP %{http_code}\n' -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -X PUT \
  https://registry.npmjs.org/probe-$(date +%s) \
  -d '{"_id":"probe","name":"probe","versions":{}}'
```

* `400` / `409` — право есть (тело запроса неполное, это ожидаемо);
* `403` с телом `Package name triggered spam detection` — **тоже право есть**:
  запрос авторизован, отказ по содержимому;
* `403` с `Two-factor authentication ... is required` — права нет;
* `401` — токен не принят.

---

## 3. Публикация в npm

```bash
tools/preflight.sh . Gdenich/my-dsh-plugin   # должен пройти
npm publish                                  # без --dry-run: только он проверяет право
```

Что учесть:

* **`npm publish --dry-run` право не проверяет** — он печатает состав тарбола и
  выходит с нулём даже без доступа. Проверяйте доступ пробной записью выше.
* **Новый аккаунт проходит проверку безопасности.** После `npm publish` в логе
  появляется `Your package is being processed and may take a few minutes`, и
  версия появляется в реестре **через 3-7 минут**. Это не ошибка — не публикуйте
  повторно, дождитесь.
* **Текст README попадает на страницу пакета из опубликованной версии.**
  Отредактировать его отдельно нельзя: правка README требует нового релиза.
  Поэтому держите в README то, что должен видеть читатель пакета, а
  инструкции для мейнтейнера — в комментариях к workflow.
* **Свежий релиз не устанавливается сразу.** У pnpm есть политика минимального
  возраста релиза: `dsh plugin add my-dsh-plugin` поставит предыдущую версию.
  Точная версия (`my-dsh-plugin@0.1.2`) ставится немедленно.

---

## 4. GitHub

```bash
git init -q
git add -A
git commit -m "Initial release"
gh repo create my-dsh-plugin --public --source=. --remote=origin \
  --description "Короткое описание для страницы репозитория" --push
gh repo edit --add-topic dsh --add-topic deepseek-harness --add-topic dsh-plugin
```

Проверить, что репозиторий действительно публичный, а не только по настройке:

```bash
gh repo view Gdenich/my-dsh-plugin --json visibility,isPrivate
curl -s -o /dev/null -w '%{http_code}\n' https://github.com/Gdenich/my-dsh-plugin
curl -s -o /dev/null -w '%{http_code}\n' https://raw.githubusercontent.com/Gdenich/my-dsh-plugin/master/README.md
```

Установка из GitHub работает сразу, без реестра:

```bash
dsh plugin --profile web add github:Gdenich/my-dsh-plugin
```

Собирать на месте нечего (бандл уже собран), поэтому `allowBuilds` в pnpm не
нужен — но и `prepare`-скриптов быть не должно, иначе pnpm их заблокирует.

---

## 5. Автопубликация по тегу

`.github/workflows/publish.yml`:

```yaml
name: publish
on:
  push:
    tags: ["v*"]
permissions:
  contents: read
  id-token: write          # provenance
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          registry-url: https://registry.npmjs.org
      - name: Tag must match the manifest version
        run: |
          tag="${GITHUB_REF_NAME#v}"
          version="$(node -p "require('./package.json').version")"
          [ "$tag" = "$version" ] || { echo "tag $GITHUB_REF_NAME != $version" >&2; exit 1; }
      - name: Tests must pass on a fresh clone
        run: npm test
      - name: Tarball carries only the runtime files
        run: npm publish --dry-run
      - name: Publish
        run: npm publish --provenance --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

Секрет:

```bash
printf '%s' "$(cat ~/.npmrc | sed -n 's|.*_authToken=||p')" | gh secret set NPM_TOKEN --repo Gdenich/my-dsh-plugin
```

Релиз — **только аннотированным тегом**:

```bash
npm version patch -m "Release %s"        # создаёт аннотированный тег
git push origin master --follow-tags
```

> **Ловушка.** `git tag v1.0.1` создаёт *лёгкий* тег, а `git push --follow-tags`
> отправляет только аннотированные. Workflow молча не запустится, и вы будете
> искать причину в YAML. `npm version` создаёт правильный тег сам.

> **Ловушка.** Тесты в CI выполняются на свежем клоне. Если тест читает файл,
> которого нет в git (например `build/` в `.gitignore`), job упадёт с
> `FileNotFoundError`. Проверяйте, что тесты самодостаточны: наш тест бандла
> достаёт данные прямо из закоммиченного артефакта и только при наличии
> локального `build/` дополнительно сверяется с ним.

---

## 6. Чужой плагин публиковать нельзя

Если плагин уже есть в реестре — он чей-то. Проверка перед началом:

```bash
npm view my-dsh-plugin maintainers homepage
```

* если это ваш пакет — публикуйте новую версию;
* если чужой, а вам нужны правки — делайте **форк** (`gh repo fork`), меняйте
  поведение и публикуйте под **своим** именем (`@gdenich/my-dsh-plugin`),
  сохранив копирайт автора и ссылку на исходный репозиторий в LICENSE и README;
* если правок нет — ничего публиковать не нужно, оригинал уже ставится одной
  командой.

Версию, которая уже занята, npm не примет — сначала бампнуйте.

---

## 7. Порядок целиком

```bash
# 1. манифест и патч в порядке
tools/preflight.sh . Gdenich/my-dsh-plugin

# 2. доступ к npm (один раз на машину)
read -rs NPM_TOKEN && export NPM_TOKEN && tools/set-npm-token.sh

# 3. первый релиз
npm publish

# 4. репозиторий
git init -q && git add -A && git commit -m "Initial release"
gh repo create my-dsh-plugin --public --source=. --remote=origin --push

# 5. автопубликация на будущее
gh secret set NPM_TOKEN --repo Gdenich/my-dsh-plugin < <(sed -n 's|.*_authToken=||p' ~/.npmrc)
# положить .github/workflows/publish.yml из раздела 5

# 6. следующие версии
npm version patch -m "Release %s" && git push origin master --follow-tags

# 7. проверить, что релиз доехал (в реестре появляется не сразу)
for i in $(seq 1 12); do
  v=$(npm view my-dsh-plugin version); echo "$i: $v"
  [ "$v" = "$(node -p "require('./package.json').version")" ] && break
  sleep 30
done

# 8. проверка установкой на чистом профиле
DSH_HOME=/tmp/check-$$ dsh plugin --profile web add my-dsh-plugin
```

---

## 8. Проверка `desktop`-профиля

CLI этот профиль не трогает: `profile "desktop" is managed exclusively by the
Electron application`. Манифест правится напрямую, а `bundles` дописывается
руками:

```bash
cd ~/.dsh/profiles/desktop
ln -s /path/to/my-dsh-plugin node_modules/my-dsh-plugin
# в package.json: "my-dsh-plugin": "link:/path/to/my-dsh-plugin" в dependencies
#                 и "my-dsh-plugin" в dsh.profile.bundles
```

Правка безопасна: список `bundles`, переставший совпадать с шаблоном поставки,
приложение считает пользовательским и не перезаписывает. После — **перезапуск
DSH Desktop**: список плагинов читается при загрузке профиля.

---

## Чек-лист перед публикацией

- [ ] `dsh.bundle.patch` указан, файл существует, `insert:` внутри есть
- [ ] `id` в патче = `id` в бандле = `module.exports.name`
- [ ] для клиентского плагина: бандл собран и закоммичен, без плейсхолдеров
- [ ] все внешние зависимости бандла перечислены в `dsh.client.inject`
- [ ] `files[]` перечисляет только нужное и всё перечисленное существует
- [ ] `README.md` и `LICENSE` на месте, README описывает установку
- [ ] `repository`, `homepage`, `bugs` указывают на реальный репозиторий
- [ ] версия не занята в реестре, имя пакета — ваше
- [ ] `tools/preflight.sh` проходит без FAIL
- [ ] тесты проходят на свежем клоне (`npm test` на копии без игнорируемых каталогов)
- [ ] секрет `NPM_TOKEN` положен в репозиторий
- [ ] релиз помечен **аннотированным** тегом
