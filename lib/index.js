// lib/index.js — host half of dsh-ru-ui.
//
// The translation itself lives entirely in the browser bundle: dictionaries are
// registered into the client locale runtime and the language catalog is
// extended there. The host half exists only so the loader has a plugin row to
// mount, which is what makes the client-modules scanner offer this package's
// bundle to the page.
//
// Keeping the host inert is deliberate. It means no settings namespace, no HTTP
// route, and no host state to migrate — the durable language preference stays
// owned by DSH's own locale plugin, so this plugin can be removed at any time
// without leaving anything behind.

/** Loader row name; must match the id the client bundle registers. */
export const name = 'dsh-ru-ui'

/**
 * Mount the plugin.
 *
 * Nothing to configure: the browser half performs registration and activation
 * on its own. `inject` stays empty so the plugin can never be the reason a
 * profile fails to boot.
 */
export function apply() {}
