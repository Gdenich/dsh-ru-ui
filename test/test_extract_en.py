#!/usr/bin/env python3
"""Fixture tests for the bundle dictionary extractor.

Run: python3 test/test_extract_en.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import extract_en as E  # noqa: E402

FAILURES: list[str] = []


def check(name: str, got, want) -> None:
    if got != want:
        FAILURES.append(f"{name}\n    got:  {got!r}\n    want: {want!r}")


# 1. Declared names, pair form with shorthand keys (the ui-conversation shape).
SHORTHAND = '''
const NS = "conversation";
const zh = { "a": "甲" };
const en = { "a": "one", "b": "two" };
function apply(ctx) {
  ctx.effect(() => ctx.locale.register(NS, { zh, en }), "dictionaries");
}
'''
import tempfile  # noqa: E402


def harvest(source: str) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(source)
        path = fh.name
    try:
        return E.harvest_file(path)
    finally:
        os.unlink(path)


check("shorthand pair form", harvest(SHORTHAND), {"conversation": {"a": "one", "b": "two"}})

# 2. Identifier namespaces and spread composition.
SPREAD = '''
const BASE = { "x": "ex" };
const NS2 = "settings.models";
const zh = { "y": "歪" };
const en = { ...BASE, "y": "why" };
locale.register(NS2, { zh, en });
'''
check("spread composition", harvest(SPREAD), {"settings.models": {"x": "ex", "y": "why"}})

# 3. Phase form with an identifier dictionary.
PHASE = '''
const LOCALE_NS = "chat-import";
const en = { "trigger": "Import" };
locale.register(LOCALE_NS, "en", en);
locale.register(LOCALE_NS, "zh", { "trigger": "导入" });
'''
check("phase form", harvest(PHASE), {"chat-import": {"trigger": "Import"}})

# 4. Literal namespace + literal dictionary, template/comment noise around it.
LITERAL = '''
/* a comment with } and { and "quotes" */
const css = "a{b}c";
locale.register("dsh-cron", "en", { "sidebar.label": "Scheduled tasks" });
'''
check("literal namespace", harvest(LITERAL), {"dsh-cron": {"sidebar.label": "Scheduled tasks"}})

# 5. A `.register(` that is not the locale runtime must not be harvested.
FOREIGN = '''
const NS = "side";
const registry = { register(k, v) {} };
registry.register(NS, { "k": "v" });
'''
check("foreign register ignored", harvest(FOREIGN), {})

# 6. The per-module locale file declares the pairs; apply.js registers them.
CROSS_MODULE = '''
//#region lib/types/client/locales.js
const NS = "conversation";
const zh = { "a": "甲" };
const en = { "a": "one", "b": "two" };
//#endregion
//#region lib/types/client/apply.js
const en$1 = en;
const zh$1 = zh;
locale.register(NS, { zh: zh$1, en: en$1 });
//#endregion
'''
check("cross-module alias", harvest(CROSS_MODULE), {"conversation": {"a": "one", "b": "two"}})

# 7. Pair-loop form.
LOOP = '''
const LOCALE_NS = "loop-ns";
for (const [locale, dict] of pairs) register(LOCALE_NS, locale, dict);
const pairs = [["en", { "k": "v" }], ["zh", { "k": "值" }]];

'''
check("pair loop", harvest(LOOP), {"loop-ns": {"k": "v"}})

# 8. Escapes survive intact.
ESCAPES = r'''
const NS = "esc";
const en = { "q": "quote \" inside", "n": "line\nbreak", "u": "…" };
locale.register(NS, { zh: {}, en });
'''
check("escapes", harvest(ESCAPES), {"esc": {"q": 'quote " inside', "n": "line\nbreak", "u": "…"}})

if FAILURES:
    print("FAIL\n" + "\n".join(FAILURES))
    raise SystemExit(1)
print("extract_en: all checks passed")
