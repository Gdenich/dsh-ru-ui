/* eslint-disable */
// lib/client.template.js — source of truth for the generated lib/client.js.
//
// DSH client bundles are plain CJS factories registered into the page's module
// loader; every side effect lives inside the factory closure and runs when the
// runtime materializes the module. `require` resolves only the packages named
// in package.json `dsh.client.inject`, so the dictionary is inlined at build
// time by tools/gen_dict_js.py rather than required as a sibling file.
//
// What this plugin does, and nothing else:
//   1. registers its Russian dictionaries into the shared locale runtime,
//   2. adds `ru` to the language catalog so Settings -> General -> Language
//      offers it,
//   3. activates Russian on first run, honouring an explicit prior choice.
//
// It deliberately does not wrap `translate`, patch DOM text, or ship any Smart
// UX feature: the interface translation is the whole product.
window.__ModuleLoader__.load({
  id: 'dsh-ru-ui',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports

    /**
     * namespace -> { English key -> Russian string }.
     * Inlined by tools/gen_dict_js.py; never edit this literal by hand.
     */
    const DICT = __DICTIONARY__

    /** Locale id and the label shown in the Language picker. */
    const LOCALE_ID = 'ru'
    const LOCALE_LABEL = 'Русский'
    /** English is the only locale DSH guarantees, so it is the fallback. */
    const FALLBACK_ID = 'en'
    /** Settings namespace and field the locale runtime stores its choice in. */
    const LOCALE_NS = 'locale'
    const LOCALE_FIELD = 'preference'
    /** BCP 47 tag written to <html lang> by the locale runtime itself. */
    const HTML_LANG = 'ru-RU'

    /** Registry payload shape guard: a namespace maps keys to strings. */
    const isDict = (value) =>
      value !== null && typeof value === 'object' && !Array.isArray(value)

    /**
     * Read the durable locale preference, or undefined when the user has never
     * picked a language. The snapshot is undefined while settings are still
     * loading, which must not be mistaken for "no preference".
     * @param scope - a bound settings scope for the locale namespace.
     * @returns the stored locale id, or undefined.
     */
    const storedPreference = (scope) => {
      if (!scope) return undefined
      try {
        const snapshot = scope.getSnapshot()
        const value = snapshot && snapshot.value
        if (!value || typeof value !== 'object') return undefined
        const stored = value[LOCALE_FIELD]
        return typeof stored === 'string' && stored !== '' ? stored : undefined
      } catch (err) {
        return undefined
      }
    }

    /** Whether the settings mirror has answered yet. */
    const preferencesReady = (scope) => {
      try {
        const snapshot = scope.getSnapshot()
        return Boolean(snapshot) && snapshot.status !== 'loading'
      } catch (err) {
        return false
      }
    }

    function apply(ctx) {
      const runtime = ctx.get('locale')
      if (!runtime) {
        console.warn('[dsh-ru-ui] locale service unavailable; Russian not registered')
        return
      }

      // 1. Dictionaries. One disposer per namespace, tied to this plugin's
      //    lifecycle so an HMR reload or a disable cannot leave half a
      //    dictionary behind.
      let registered = 0
      for (const ns of Object.keys(DICT)) {
        const entries = DICT[ns]
        if (!isDict(entries)) continue
        ctx.effect(() => {
          try {
            return runtime.register(ns, LOCALE_ID, entries)
          } catch (err) {
            console.warn(`[dsh-ru-ui] could not register namespace "${ns}"`, err)
            return () => {}
          }
        }, `dsh-ru-ui: dictionary ${ns}`)
        registered += 1
      }

      // 2. Language catalog. Re-registering an occupied id throws, which is the
      //    honest outcome when another Russian pack already owns the id.
      const alreadyRegistered = runtime
        .getLocale()
        .locales.some((locale) => locale.id === LOCALE_ID)
      if (!alreadyRegistered) {
        try {
          runtime.addLanguage({ id: LOCALE_ID, label: LOCALE_LABEL, fallback: FALLBACK_ID })
        } catch (err) {
          console.warn('[dsh-ru-ui] could not add the Russian locale', err)
          return
        }
      }

      // 3. Activation. The locale runtime owns the durable preference, so this
      //    plugin only decides whether to write it once and then stays out of
      //    the way — an explicit choice in the Language picker always wins.
      const scope = (() => {
        try {
          return ctx.settingsScope
            ? ctx.settingsScope.bind({ namespace: LOCALE_NS })
            : null
        } catch (err) {
          return null
        }
      })()

      let activated = false
      const activate = (reason) => {
        if (activated) return
        activated = true
        try {
          const result = runtime.setLocale(LOCALE_ID)
          console.info(`[dsh-ru-ui] Russian interface activated (${reason})`)
          // setLocale returns a promise when the runtime persists the choice.
          if (result && typeof result.catch === 'function') {
            result.catch((err) => {
              console.warn('[dsh-ru-ui] locale choice not persisted', err)
            })
          }
        } catch (err) {
          console.warn('[dsh-ru-ui] could not activate Russian', err)
        }
      }

      const decide = () => {
        if (runtime.getLocale().active === LOCALE_ID) {
          activated = true
          return
        }
        if (!preferencesReady(scope)) return
        // An explicit choice — including English, made in the Language picker
        // or by removing this plugin — is never overridden. Installing a
        // Russian language pack IS the request for a Russian interface, so the
        // first run switches without asking.
        if (storedPreference(scope) !== undefined) return
        activate('first run')
      }

      decide()

      // The settings mirror may still be loading on the first pass; re-decide
      // when it lands. `activated` keeps this idempotent.
      if (!activated && scope) {
        ctx.effect(() => scope.subscribe(decide), 'dsh-ru-ui: activation')
      }

      // Keep <html lang> in step when the user switches language, so browser
      // spell-check and hyphenation follow the interface.
      ctx.effect(
        () =>
          runtime.subscribe(() => {
            const active = runtime.getLocale().active
            document.documentElement.lang = active === LOCALE_ID ? HTML_LANG : active
          }),
        'dsh-ru-ui: document language',
      )

      module.exports.__registered = registered
    }

    module.exports.name = 'dsh-ru-ui'
    module.exports.inject = ['locale', 'settingsScope']
    module.exports.apply = apply
    return module.exports
  },
})
