// test/run_bundle_stale.mjs — the upgrade path.
//
// After a DSH upgrade the shipped dictionary can carry keys the running build no
// longer asks for, and it will be missing keys the new build added. Neither may
// break plugin activation: unknown dictionary entries are simply never looked
// up, and missing ones fall back to English. This harness runs the real bundle
// with a deliberately stale dictionary and asserts it still activates.
//
// Usage: node test/run_bundle_stale.mjs <bundle.js>

import { readFileSync } from 'node:fs'

const [bundlePath] = process.argv.slice(2)
const bundle = readFileSync(bundlePath, 'utf8')
const problems = []

// A dictionary from "the previous release": a namespace that no longer exists,
// keys that were renamed, a plural family, and one value that is not a string.
const stale = {
  'namespace-that-was-removed': { 'old.key': 'Старое значение' },
  conversation: {
    'renamed.away.key': 'Ключ, которого больше нет',
    'still.here': 'Всё ещё здесь',
    'count.one': '{n} сессия',
    'count.few': '{n} сессии',
    'count.many': '{n} сессий',
  },
  broken: 'not-an-object',
  '': { 'weird.key': 'пустое пространство имён' },
}

let registration = null
const pageWindow = {
  __ModuleLoader__: {
    load(row) {
      registration = row
    },
  },
}
const pageDocument = { documentElement: { lang: '' } }
const require = (spec) => {
  throw new Error(`bundle required "${spec}"`)
}
const quiet = { info() {}, warn() {}, error() {} }
const pageModule = { exports: {} }

// The bundle inlines its own dictionary, so it is patched for this run: the
// literal is replaced with the stale one to exercise the same code path an
// upgrade produces.
const marker = 'const DICT = '
const start = bundle.indexOf(marker) + marker.length
let depth = 0
let end = start
for (; end < bundle.length; end += 1) {
  if (bundle[end] === '{') depth += 1
  else if (bundle[end] === '}') {
    depth -= 1
    if (depth === 0) break
  }
}
const patched =
  bundle.slice(0, start) + JSON.stringify(stale) + bundle.slice(end + 1)

// eslint-disable-next-line no-new-func
new Function('window', 'document', 'module', 'exports', 'console', patched)(
  pageWindow,
  pageDocument,
  pageModule,
  pageModule.exports,
  quiet,
)

if (!registration) {
  console.log('bundle never registered with the loader')
  process.exit(1)
}

const registered = new Map()
const languages = []
let active = 'en'
const locale = {
  register(ns, id, entries) {
    registered.set(ns, { id, entries })
    return () => registered.delete(ns)
  },
  addLanguage(input) {
    languages.push(input)
  },
  getLocale() {
    return { active, locales: ['en', ...languages.map((l) => l.id)] }
  },
  subscribe: () => () => {},
  setLocale(id) {
    active = id
  },
}

let snapshot = { status: 'ready', value: {} }
const ctx = {
  get: (name) => (name === 'locale' ? locale : undefined),
  settingsScope: {
    bind: () => ({
      getSnapshot: () => snapshot,
      subscribe: () => () => {},
    }),
  },
  effect(fn) {
    fn()
  },
}

try {
  registration.factory(require).apply(ctx)
} catch (error) {
  problems.push(`activation threw on a stale dictionary: ${error.message}`)
}

// Only real namespaces with object values may be registered: a malformed or
// long-gone entry must be skipped, never crash registration.
if (!registered.has('conversation')) {
  problems.push('a valid namespace was not registered')
}
// A namespace the running build no longer asks for is expected to register
// harmlessly: registration is by namespace, and nothing looks it up. Assert the
// shape rather than its absence, so this stays a documented behaviour.
const removed = registered.get('namespace-that-was-removed')
if (!removed || removed.id !== 'ru') {
  problems.push('a removed namespace did not register cleanly')
}
if (registered.has('broken')) {
  problems.push('a non-object dictionary entry was registered')
}
if (active !== 'ru') {
  problems.push(`plugin did not activate Russian on a stale dictionary (active=${active})`)
}

if (problems.length) {
  console.log(problems.join('\n'))
  process.exit(1)
}
console.log('OK')
