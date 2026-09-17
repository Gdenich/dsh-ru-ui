// test/run_bundle.mjs — execute lib/client.js against a stub DSH page loader.
//
// The real page evaluates the bundle as a script and hands the factory a
// `require` resolving only declared externals. This harness mirrors that
// contract and asserts what the plugin promises to the locale runtime:
//   * every namespace in build/ru.json is registered under the `ru` locale,
//   * the language is added to the catalog with the `en` fallback,
//   * activation happens when the user has never chosen a language,
//   * an explicit stored choice is never overridden.
//
// Usage: node test/run_bundle.mjs <bundle.js> <ru.json>

import { readFileSync } from 'node:fs'

const [bundlePath, dictPath] = process.argv.slice(2)

const bundle = readFileSync(bundlePath, 'utf8')
const dict = JSON.parse(readFileSync(dictPath, 'utf8')).namespaces
const problems = []

// --- Stub page loader -------------------------------------------------------
let registration = null
const pageWindow = {
  __ModuleLoader__: {
    load(row) {
      registration = row
    },
  },
}
const pageDocument = { documentElement: { lang: '' } }
const pageNavigator = { languages: ['en-US'], language: 'en-US' }

// The dictionary is inlined, so no external package may be required.
const require = (spec) => {
  throw new Error(`bundle required "${spec}" — the dictionary must be inlined`)
}

// The plugin logs its activation; keep stdout reserved for the verdict.
const quiet = { info() {}, warn() {}, error() {} }
const pageModule = { exports: {} }
// eslint-disable-next-line no-new-func
// eslint-disable-next-line no-new-func
new Function('window', 'document', 'navigator', 'module', 'exports', 'console', bundle)(
  pageWindow,
  pageDocument,
  pageNavigator,
  pageModule,
  pageModule.exports,
  quiet,
)

if (!registration) {
  console.log('bundle never called window.__ModuleLoader__.load')
  process.exit(1)
}
if (registration.id !== 'dsh-ru-ui') {
  problems.push(`loader id is ${JSON.stringify(registration.id)}, expected "dsh-ru-ui"`)
}

const exported = registration.factory(require)
for (const field of ['name', 'inject', 'apply']) {
  if (exported[field] === undefined) problems.push(`module.exports.${field} is missing`)
}
if (exported.name !== 'dsh-ru-ui') problems.push(`name is ${exported.name}`)
if (!exported.inject?.includes('locale')) problems.push('inject does not declare "locale"')

// --- Stub locale runtime ----------------------------------------------------
const registered = new Map()
const effects = []
const settingsListeners = new Set()
const languages = ['en']
let active = 'en'
let setLocaleCalls = 0

const locale = {
  register(ns, id, entries) {
    if (registered.has(ns)) throw new Error(`duplicate namespace ${ns}`)
    registered.set(ns, { id, entries })
    return () => registered.delete(ns)
  },
  addLanguage(input) {
    languages.push(input)
  },
  getLocale() {
    return { active, locales: [...languages] }
  },
  subscribe() {
    return () => {}
  },
  setLocale(id) {
    if (id !== 'ru') throw new Error(`cannot switch to unregistered locale ${id}`)
    setLocaleCalls += 1
    active = id
  },
}

// The mirror answers "ready, but the user never chose a language".
let snapshot = { status: 'ready', value: {} }
const scope = {
  getSnapshot: () => snapshot,
  subscribe(fn) {
    settingsListeners.add(fn)
    return () => settingsListeners.delete(fn)
  },
}

const ctx = {
  get: (name) => (name === 'locale' ? locale : undefined),
  settingsScope: { bind: () => scope },
  effect(fn) {
    effects.push(fn())
  },
}

exported.apply(ctx)

// --- Assertions -------------------------------------------------------------
const expectedNamespaces = Object.keys(dict)
if (registered.size !== expectedNamespaces.length) {
  problems.push(
    `registered ${registered.size} namespaces, expected ${expectedNamespaces.length}`,
  )
}
for (const ns of expectedNamespaces) {
  const row = registered.get(ns)
  if (!row) {
    problems.push(`namespace ${ns} was not registered`)
  } else if (row.id !== 'ru') {
    problems.push(`namespace ${ns} registered under ${row.id}, expected "ru"`)
  } else if (Object.keys(row.entries).length !== Object.keys(dict[ns]).length) {
    problems.push(`namespace ${ns} entry count differs from the dictionary`)
  }
}
for (const ns of registered.keys()) {
  if (!expectedNamespaces.includes(ns)) problems.push(`unexpected namespace ${ns}`)
}

if (languages.length !== 2 || languages[1].id !== 'ru') {
  problems.push(`language catalog is ${JSON.stringify(languages)}, expected en + ru`)
} else if (languages[1].fallback !== 'en') {
  problems.push(`ru fallback is ${languages[1].fallback}, expected "en"`)
}

if (setLocaleCalls !== 1 || active !== 'ru') {
  problems.push(`activation: setLocale called ${setLocaleCalls}x, active=${active}`)
}

// The browser language must not decide activation: this run reports English.
if (pageNavigator.languages[0] !== 'en-US') {
  problems.push('harness no longer exercises the non-Russian browser path')
}

// An explicit prior choice must never be overridden: replay the decision with a
// stored preference and confirm the plugin leaves it alone.
active = 'en'
setLocaleCalls = 0
snapshot = { status: 'ready', value: { preference: 'en' } }
for (const fn of settingsListeners) fn()
if (setLocaleCalls !== 0) {
  problems.push('plugin overrode an explicit stored preference')
}

if (problems.length) {
  console.log(problems.join('\n'))
  process.exit(1)
}
console.log('OK')
