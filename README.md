# dsh-ru-ui

Russian interface for **DeepSeek Harness** (DSH). Translation only.

Registers 2,581 Russian strings across 49 namespaces for the DSH platform and its
plugins, adds **Русский** to the language picker, and switches the interface on
first run. No typography rewriting, no spell-check, no keyboard-layout fix, no
model-output translation — those belong to
[`@goodandready/dsh-russian-lang`](https://github.com/GooDAnDReaDY/dsh-russian-lang),
which this plugin takes its translations from.

```bash
dsh plugin --profile web add dsh-ru-ui
dsh plugin --profile web add github:Gdenich/dsh-ru-ui
```

Restart DSH afterwards. For the app-managed `desktop` profile, run
`tools/deploy.sh desktop` (the CLI refuses that profile by design).

Dictionaries are keyed by the English source strings DSH passes to its locale, so
a DSH upgrade degrades gracefully to partial English instead of a broken
interface. `npm run refresh` re-extracts and rebuilds for a specific DSH build.

Canonical documentation is in Russian below (`README.md`); this section is the
English summary.

---

Русский интерфейс для **DeepSeek Harness** (DSH) — только перевод, без ничего лишнего.

Плагин добавляет в DSH полноценный русский язык: словари для ядра и плагинов,
пункт «Русский» в списке языков и автоматическое переключение при первом запуске.

```text
Установили  →  интерфейс на русском.  Одна настройка — и обратно на English.
```

## Что делает

* **Регистрирует русские словари.** 2 581 строка интерфейса в 49 пространствах
  имён: диалог, настройки, модели, боковые панели, трейс рассуждений, планировщик,
  магазин плагинов, контекст, сессии, субагенты, универсальный офис и другое.
* **Добавляет язык.** В «Настройки → Общие → Язык» появляется «Русский».
* **Включает русский при первом запуске.** Если язык ещё ни разу не выбирали,
  интерфейс переключается сам. Явный выбор — в том числе English — никогда не
  переопределяется.
* **Синхронизирует `<html lang>`.** Проверка орфографии и переносы в браузере
  следуют языку интерфейса.

## Чего он НЕ делает

Это осознанно минимальный плагин. В нём нет:

* автозамены типографики в ответах модели и в поле ввода;
* восстановления буквы «ё»;
* исправления раскладки по `Alt+L` и индикатора раскладки;
* русских алиасов слэш-команд;
* перевода сообщений ассистента (LibreTranslate / Google);
* русского системного промпта агента;
* экспорта диалога в Markdown;
* своей карточки настроек и обновлятора.

Если что-то из этого нужно — это
[`@goodandready/dsh-russian-lang`](https://github.com/GooDAnDReaDY/dsh-russian-lang),
из которого взяты сами переводы. Здесь оставлен только перевод интерфейса.

## Установка

Плагин — обычная зависимость профиля DSH. Он объявляет `dsh.bundle.patch`,
поэтому штатный CLI не только ставит пакет, но и **сам дописывает** его в
`dsh.profile.bundles` (реконсиляция по установленному состоянию).

```bash
# из реестра npm
dsh plugin --profile web add dsh-ru-ui

# прямо из GitHub
dsh plugin --profile web add github:Gdenich/dsh-ru-ui

# из локальной копии или архива
dsh plugin --profile web add ./dsh-ru-ui
```

Профиль создастся сам, если его ещё нет. После установки нужно **перезапустить
DSH**.

`web` замените на имя своего профиля: `tui`, `desktop` (см. ниже) или любой свой.

### Профиль `desktop` (DSH Desktop)

CLI этот профиль не трогает намеренно — им управляет приложение
(«profile "desktop" is managed exclusively by the Electron application»).
Поэтому манифест правится напрямую, а готовый скрипт делает это идемпотентно:

```bash
tools/deploy.sh desktop          # положит симлинк, допишет dependency и bundles
```

Вручную то же самое:

```bash
cd ~/.dsh/profiles/desktop
npm install --no-save dsh-ru-ui   # или: распаковать архив в node_modules/dsh-ru-ui
# в package.json: "dsh-ru-ui" в dependencies и в dsh.profile.bundles
```

Правка безопасна: список `bundles`, переставший совпадать с шаблоном поставки,
приложение считает пользовательским и не перезаписывает. После — **перезапуск
DSH Desktop**.

### Проверка

```bash
# профиль собран из ожидаемых слоёв (работает для не-desktop профилей)
dsh --profile web --dump-config | grep dsh-ru-ui
```

Надёжнее всего — открыть интерфейс: «Настройки → Общие → Язык» должен содержать
пункт «Русский», а сам интерфейс при первом запуске стать русским.

## Обновление и удаление

```bash
dsh plugin --profile web update dsh-ru-ui    # npm/git-установка
dsh plugin --profile web remove dsh-ru-ui    # bundles вычистится сам
```

Для `link:`-установки обновление — заменить содержимое каталога.

## Перенос на другую машину или профиль

Для работы нужны **только 4 файла**: `package.json`, `cordis.patch.yml`,
`lib/index.js`, `lib/client.js`. Каталоги `tools/`, `test/`, `vendor/` и `build/`
нужны только для пересборки словаря и на целевой машине бесполезны — там нет
исходных бандлов DSH, из которых извлекаются английские строки.

Собрать переносимый архив:

```bash
tools/pack.sh              # → dist/dsh-ru-ui-1.0.0.tar.gz (~60 КБ, 6 файлов)
```

Установить на целевой машине:

```bash
tar -xzf dsh-ru-ui-1.0.0.tar.gz
dsh plugin --profile web add ./dsh-ru-ui        # bundles допишется сам
# для desktop: tools/deploy.sh desktop (или правка манифеста вручную)
```

Скрипт проверяет, что содержимое архива совпадает с полем `files[]` в манифесте,
так что в поставку не просочится лишнее.

### Способы доставки

| Способ | Установка | Когда подходит |
|---|---|---|
| npm `dsh-ru-ui` | `dsh plugin add dsh-ru-ui` | много машин, обновление через `pnpm update` |
| GitHub `Gdenich/dsh-ru-ui` | `dsh plugin add github:Gdenich/dsh-ru-ui` | без публикации в реестр |
| Каталог / архив | `dsh plugin add ./dsh-ru-ui` | передача вручную, офлайн |
| `link:` на рабочий каталог | `dsh plugin add /path/to/dsh-ru-plugin` | разработка: правки в `lib/client.js` подхватываются живьём |

Собирать на месте нечего: `lib/client.js` уже собран и лежит в репозитории, а
`files[]` в манифесте ограничивает поставку шестью файлами. Поэтому для
git-установки не нужны ни `prepare`, ни разрешения в `allowBuilds`.

## Совместимость с версиями DSH

**Код плагина** от версии не зависит: он пользуется только публичным API локали
(`register`, `addLanguage`, `setLocale`, `getLocale`, `subscribe`).

**Словарь** привязан к набору строк той сборки, из которой собран. Ключи — это
английские строки, которые DSH передаёт в локаль, поэтому на другой версии:

* строки, которые есть в словаре, переводятся;
* новые строки показываются по-английски;
* исчезнувшие просто не используются.

Ничего не ломается — интерфейс становится частично английским, а не пустым или
сломанным. Это отдельно закрыто тестом `test/run_bundle_stale.mjs`: бандл с
устаревшим и даже битым словарём всё равно регистрируется и активируется.

Подтянуть перевод под свою сборку (нужны исходники пакета и установленный DSH):

```bash
npm run refresh     # переизвлечь английские строки из этой сборки и пересобрать
npm run verify      # покажет, что ещё не переведено
npm run audit       # что совпадает с английским (имена и шаблоны — норма)
```

`build_ru.py` выбрасывает устаревшие ключи и печатает, чего не хватает. Новые
строки дописываются в `vendor/ru/gap-*.json` и пересобираются; правки поверх
переносимого корпуса — в `vendor/ru/overrides.json`.

## Как это устроено

```
lib/index.js            хост-половина: пустая, нужна только чтобы загрузчик увидел плагин
lib/client.template.js  логика браузерной половины (источник правды)
lib/client.js           СОБРАННЫЙ бандл: шаблон + вшитый словарь
cordis.patch.yml        строка плагина в дереве загрузчика
tools/                  извлечение английских строк, сборка, упаковка и проверки
vendor/ru/              русские переводы (по файлу на группу пространств имён)
```

Хост-половина намеренно пустая: весь перевод живёт в браузере. Поэтому у плагина
нет ни своего пространства настроек, ни HTTP-маршрутов, ни состояния на хосте —
его можно удалить в любой момент, ничего не останется. Выбранный язык хранит
штатный плагин локали DSH (`locale.preference` в `settings.yaml`).

Словари вшиты в бандл, а не подгружаются файлом: загрузчик клиентских модулей DSH
резолвит только пакеты из `dsh.client.inject`, поэтому `require('./dict.js')` там
не работает.

## Разработка

```bash
python3 test/test_extract_en.py   # фикстуры парсера бандлов
python3 test/test_bundle.py       # сборка воспроизводима + бандл проходит стаб-загрузчик
```

`test_bundle.py` проверяет, что `lib/client.js` побайтово воспроизводится из
`build/ru.json`, что вшитый словарь совпадает с исходным и что бандл при
исполнении регистрирует все пространства имён под локалью `ru`, добавляет язык и
включает русский ровно один раз.

## Проверено

* 2 581 строка, 49 пространств имён, 0 пропусков в DSH 0.1.5-rc.2.
* Бандл отдаётся странице, словарь доезжает без искажений (побайтовое сравнение
  отданного и собранного словаря), порядок инъекции
  (`dsh-client-locale` → `dsh-client-ui-settings` → `dsh-ru-ui`) соблюдён.
* Русский язык появляется в списке и переключает интерфейс полностью —
  проверено на живой сборке: боковая панель, настройки, страница «Плагины»,
  контекстное меню и уведомления.
* При пустой настройке языка интерфейс включается по-русски сам, и выбор
  сохраняется в `settings.yaml`.

## Публикация

```bash
npm login        # один раз, вручную: команда интерактивная
npm publish      # уйдёт ровно 6 файлов, ничего не собирается на месте
```

Версия и тег держатся вместе:

```bash
npm version patch && git push --follow-tags
```

По тегу `v*` сработает `.github/workflows/publish.yml`: сверит тег с версией в
манифесте, проверит, что `lib/client.js` воспроизводится из словаря, прогонит
тесты бандла и опубликует с provenance. Нужен один секрет репозитория —
`NPM_TOKEN` (automation-токен npm).

## Полезные команды

```bash
npm test          # фикстуры парсера + воспроизводимость и исполнение бандла
npm run verify    # покрытие против установленной сборки DSH (0 пропусков)
npm run audit     # что ещё совпадает с английским (имена и шаблоны — норма)
npm run refresh   # пересобрать словарь после обновления DSH
npm run pack      # собрать переносимый архив dist/dsh-ru-ui-<версия>.tar.gz
npm run deploy    # прописать плагин в профиль (по умолчанию desktop)
```

## Лицензия

MIT. Русские переводы — производная от
[`@goodandready/dsh-russian-lang`](https://github.com/GooDAnDReaDY/dsh-russian-lang)
(MIT, © 2026 GooDAnDReaDY); подробности в [LICENSE](LICENSE).
