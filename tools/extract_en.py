#!/usr/bin/env python3
"""Extract English i18n dictionaries from installed DSH client bundles.

A DSH client plugin ships a hand-written CJS factory bundle
(`window.__ModuleLoader__.load({ id, factory })`). Inside it, UI copy is
registered into the shared locale runtime:

    locale.register("conversation", { zh: {...}, en: {...} })
    locale.register(NS, "en", en)
    locale.register(NS, { zh, en })
    register(NS, locale, dict)          // inside a `for ([locale, dict] of pairs)`

This module recovers the `en` half of every such call, keyed by namespace, and
records which package contributed it.

The scanners are hand-written and linear on purpose: shipped bundles reach
several megabytes of single-line minified code, where a backtracking regex over
string-literal alternatives takes minutes instead of milliseconds.

Usage:
    python3 tools/extract_en.py <install-root-or-node_modules> [output.json]
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys

# `X = "some.namespace"` — how minified bundles spell their namespace constant.
# Namespaces stay short, so the anchor keeps this linear.
ASSIGN_STR = re.compile(r"""([A-Za-z_$][\w$]{0,40})\s*=\s*(?:"([^"\n]{2,60})"|'([^'\n]{2,60})')""")
# `locale.register(` — the one registration entry point the locale runtime exposes.
REGISTER_AT = re.compile(r"\.register\s*\(")
IDENT = re.compile(r"[A-Za-z_$][\w$]*")

# String literals that cannot open a UI namespace: locales, imports, css units.
NOT_A_NAMESPACE = re.compile(r"^(?:zh|en|ru|zh-CN|zh-cn|utf-?8|application/|text/|image/|https?:|data:|\.{0,2}/)")


def _skip_string(src: str, i: int) -> int:
    """`i` indexes a quote; return the index just past the closing quote."""
    quote = src[i]
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return len(src)


def _skip_comment(src: str, i: int) -> int:
    """`i` indexes `/` of `//` or `/*`; return the index past the comment."""
    if src.startswith("//", i):
        end = src.find("\n", i)
        return len(src) if end < 0 else end + 1
    end = src.find("*/", i + 2)
    return len(src) if end < 0 else end + 2


def _skip_template(src: str, i: int) -> int:
    """Skip a backtick template, tolerating `${ ... }` nesting."""
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        i += 1
    return len(src)


def _match_brace(src: str, brace: int) -> int:
    """Index just past the `}` closing the `{` at `brace` (string-aware)."""
    depth, i = 0, brace
    while i < len(src):
        c = src[i]
        if c == '"' or c == "'":
            i = _skip_string(src, i)
            continue
        if c == "`":
            i = _skip_template(src, i)
            continue
        if c == "/" and i + 1 < len(src) and src[i + 1] in "/*":
            i = _skip_comment(src, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _match_bracket(src: str, bracket: int) -> int:
    """Index just past the `]` closing the `[` at `bracket` (string-aware)."""
    depth, i = 0, bracket
    while i < len(src):
        c = src[i]
        if c == '"' or c == "'":
            i = _skip_string(src, i)
            continue
        if c == "`":
            i = _skip_template(src, i)
            continue
        if c == "/" and i + 1 < len(src) and src[i + 1] in "/*":
            i = _skip_comment(src, i)
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _slice_brace(src: str, brace: int) -> str | None:
    end = _match_brace(src, brace)
    return None if end < 0 else src[brace:end]


def _unescape(raw: str) -> str:
    """Decode a JS string literal body (already stripped of its quotes).

    `raw` keeps the source escapes, so it is re-quoted verbatim for JSON — the
    one escape table that matches JavaScript for the sequences bundles emit.
    """
    if "\\" not in raw:
        return raw
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return raw


def parse_dict(text: str | None) -> dict[str, str]:
    """Parse one `{...}` object literal into a flat key -> value map.

    Keys may be quoted (`"chat.loadError"`) or bare identifiers (`nav`), which
    is what the bundler emits whenever the key is a valid identifier. Only
    string values count: an object or array value belongs to a nested structure
    and is skipped whole, so its entries never leak upward.
    """
    out: dict[str, str] = {}
    if not text:
        return out
    opening = text.find("{")
    if opening < 0:
        return out
    closing = _match_brace(text, opening)
    if closing < 0:
        return out

    i, n = opening + 1, closing - 1
    while i < n:
        c = text[i]
        if c == '"' or c == "'":
            key_start = i
            i = _skip_string(text, i)
            key = _unescape(text[key_start + 1 : i - 1])
        elif c.isalpha() or c in "_$":
            ident = IDENT.match(text, i)
            key = ident.group(0)
            i = ident.end()
        else:
            if c in "{[":
                end = _match_brace(text, i) if c == "{" else _match_bracket(text, i)
                i = end if end > 0 else i + 1
                continue
            if c == "`":
                i = _skip_template(text, i)
                continue
            if c == "/" and i + 1 < n and text[i + 1] in "/*":
                i = _skip_comment(text, i)
                continue
            i += 1
            continue

        j = _skip_ws_n(text, i, n)
        if j >= n or text[j] != ":":
            i = j
            continue
        j = _skip_ws_n(text, j + 1, n)
        if j < n and text[j] in "\"'":
            val_start = j
            j = _skip_string(text, j)
            out[key] = _unescape(text[val_start + 1 : j - 1])
        i = j
    return out


def _skip_ws_n(text: str, i: int, limit: int) -> int:
    """Whitespace skip bounded by `limit` (the object literal's closing brace)."""
    while i < limit and text[i] in " \t\r\n":
        i += 1
    return i


def object_by_ident(src: str, ident: str) -> str | None:
    """Return the first `ident = { ... }` object literal carrying quoted keys.

    Both identifier boundaries are checked, because minified bundles reuse a
    stem across distinct bindings (`en`, `en$3`, `en$4`): matching a substring
    would silently resolve the wrong dictionary.
    """
    start = 0
    while True:
        at = src.find(ident, start)
        if at < 0:
            return None
        start = at + 1
        if at and (src[at - 1].isalnum() or src[at - 1] in "_$."):
            continue
        after = at + len(ident)
        if after < len(src) and (src[after].isalnum() or src[after] in "_$"):
            continue
        j = after
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j >= len(src) or src[j] != "=" or src.startswith("==", j):
            continue
        j += 1
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j >= len(src) or src[j] != "{":
            continue
        body = _slice_brace(src, j)
        if body and ('"' in body or "'" in body):
            return body


def _skip_ws(text: str, i: int) -> int:
    """Index of the first non-whitespace character at or after `i`."""
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def _en_targets(body: str):
    """Yield what each `en` mention in a `{ zh, en }` object points at.

    A mention is a whole word `en` followed by either `:` (an explicit value) or
    a delimiter (the shorthand binding). Yields `("brace", index)` for an inline
    literal, `("ident", name)` for a named binding; an `en` followed by anything
    else (another word, a method call) is not a dictionary reference and is
    skipped rather than ending the search.
    """
    i = 0
    while True:
        at = body.find("en", i)
        if at < 0:
            return
        i = at + 2
        before = body[at - 1] if at else " "
        after = body[at + 2] if at + 2 < len(body) else " "
        if before.isalnum() or before in "_$":
            continue
        if after.isalnum() or after in "_$":
            continue
        j = _skip_ws(body, at + 2)
        if j < len(body) and body[j] == ":":
            j = _skip_ws(body, j + 1)
            if j < len(body) and body[j] == "{":
                yield "brace", j
            elif j < len(body):
                ident = IDENT.match(body, j)
                if ident:
                    yield "ident", ident.group(0)
        elif j >= len(body) or body[j] in ",}":
            # Shorthand: the `en` binding sits directly before the delimiter.
            yield "ident", "en"


def _macro_body(src: str, ident: str) -> str | None:
    """Resolve `ident` to a dictionary, following `const ident = DONOR` aliases.

    Locale modules are bundled per module: `locales.js` declares the pairs and
    `apply.js` registers them, sometimes through a local re-export. A plain
    object lookup misses that indirection, so single-assignment aliases are
    followed a bounded number of hops.
    """
    seen: set[str] = set()
    current = ident
    for _ in range(4):
        donor = object_by_ident(src, current)
        if donor is not None:
            return donor
        if current in seen:
            return None
        seen.add(current)
        follow = re.search(
            r"(?:^|[\s,;(])%s\s*=\s*([A-Za-z_$][\w$]*)\s*[;,)]" % re.escape(current), src
        )
        if follow is None:
            return None
        current = follow.group(1)
    return None


def resolve_en(src: str, body: str) -> dict[str, str]:
    """Recover the `en` half of a `{ zh, en }` or `{ zh, en: {...} }` object.

    Three shapes occur in shipped bundles: an inline literal, a named binding
    (`en`, `en$3`, `xe`), and a spread composition over another dictionary. The
    probe walks each `en` mention until one actually yields entries, so an
    unrelated identifier that merely starts with `en` cannot end the search.
    """
    out: dict[str, str] = {}
    for kind, target in _en_targets(body):
        if kind == "brace":
            chunk = _slice_brace(body, target)
            if chunk is None:
                continue
            out.update(parse_dict(chunk))
            out.update(_spread_entries(src, chunk))
        else:
            donor = _macro_body(src, target)
            if donor is None:
                continue
            out.update(parse_dict(donor))
            out.update(_spread_entries(src, donor))
        if out:
            return out
    return out


def _spread_entries(src: str, chunk: str) -> dict[str, str]:
    """Entries pulled in by `...DONOR` / `...DONOR.SECTION` inside one literal."""
    out: dict[str, str] = {}
    for sm in re.finditer(r"\.\.\.\s*([A-Za-z_$][\w$]*)(?:\s*\.\s*([A-Za-z_$][\w$]*))?", chunk or ""):
        donor = object_by_ident(src, sm.group(1))
        if donor is None:
            continue
        if sm.group(2):
            inner = re.search(r"\b%s\s*:\s*\{" % re.escape(sm.group(2)), donor)
            donor = _slice_brace(donor, inner.end() - 1) if inner else None
        out.update(parse_dict(donor))
    return out


_CANDIDATES: dict[str, dict[str, list[tuple[int, str]]]] = {}


def _cache_key(src: str) -> str:
    """Stable content key for the per-bundle caches.

    Keying on `id(src)` is unsafe: CPython reuses the address of a collected
    string, so a later bundle can read a previous bundle's cached scan. Hashing
    the bytes costs microseconds against scans measured in milliseconds.
    """
    return hashlib.sha1(src.encode("utf-8", "surrogatepass")).hexdigest()


def _candidates(src: str) -> dict[str, list[tuple[int, str]]]:
    """Every `ident = "string"` assignment in a bundle: ident -> [(offset, value)].

    Minified bundles reuse short identifiers, and the namespace constant a
    `locale.register` call passes may be declared far from the call (often
    outside its own rolldown region), so resolution keeps all candidates and
    picks by declaration order and namespace shape rather than by position alone.
    """
    key = _cache_key(src)
    cached = _CANDIDATES.get(key)
    if cached is not None:
        return cached
    found: dict[str, list[tuple[int, str]]] = {}
    for m in ASSIGN_STR.finditer(src):
        val = m.group(2) or m.group(3)
        if not val or NOT_A_NAMESPACE.match(val):
            continue
        found.setdefault(m.group(1), []).append((m.start(), val))
    if len(_CANDIDATES) > 8:
        _CANDIDATES.pop(next(iter(_CANDIDATES)))
    _CANDIDATES[key] = found
    return found


# A UI namespace: dotted lowercase words (`settings.models`, `chat-import`).
NAMESPACE_SHAPE = re.compile(r"^[A-Za-z][\w-]*(?:\.[A-Za-z][\w-]*)*$")


def pick_namespace(candidates: list[tuple[int, str]], at: int) -> str | None:
    """Choose the namespace among an identifier's candidates.

    Registration order is deliberate in DSH sources: the namespace constant is
    declared before the dictionaries it labels, so the last assignment at or
    before the call site wins; only when no such assignment exists does the
    nearest following one stand in (bundles that hoist the constant).
    """
    shaped = [(offset, value) for offset, value in candidates if NAMESPACE_SHAPE.match(value)]
    pool = shaped or list(candidates)
    before = [(offset, value) for offset, value in pool if offset <= at]
    if before:
        return max(before)[1]
    return min(pool)[1] if pool else None


def harvest_file(path: str) -> dict[str, dict[str, str]]:
    """Every namespace registered by one bundle, with its English dictionary.

    Set `DSH_RU_I18N_DIAG=1` to print why a `locale.register` call yielded
    nothing — the fastest way to find a registration shape the scanners miss.
    """
    with open(path, encoding="utf-8", errors="ignore") as fh:
        src = fh.read()

    diagnostics: list[str] = []
    names = _candidates(src)

    result: dict[str, dict[str, str]] = {}

    def add(ns: str | None, entries: dict[str, str]) -> None:
        if ns and entries:
            result.setdefault(ns, {}).update(entries)

    def namespace_at(at: int) -> str | None:
        j = at
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j >= len(src):
            return None
        if src[j] in "\"'":
            end = _skip_string(src, j)
            return _unescape(src[j + 1 : end - 1])
        ident = IDENT.match(src, j)
        if not ident:
            diagnostics.append(f"{path}: non-literal namespace at {at}")
            return None
        candidates = names.get(ident.group(0))
        if not candidates:
            diagnostics.append(f"{path}: unknown namespace identifier {ident.group(0)!r} at {at}")
            return None
        return pick_namespace(candidates, at)

    for m in REGISTER_AT.finditer(src):
        # Only the locale runtime's `register` carries dictionaries: the receiver
        # must be exactly `locale`, with no other property or identifier before it.
        head = src.rfind("locale", max(0, m.start() - 20), m.start())
        if head < 0 or not src.startswith("locale.", head):
            continue
        before = src[head - 1] if head else ""
        if before and (before.isalnum() or before in "_$"):
            continue
        ns = namespace_at(m.end())
        if ns is None:
            continue
        before_count = sum(len(v) for v in result.values())
        # A pair-loop call site resolves through its own branch below; flag only
        # calls that this iteration was responsible for.
        consumed_here = True
        # Walk the argument list to the first top-level comma.
        j = m.end()
        while j < len(src) and src[j] != ",":
            c = src[j]
            if c in "\"'":
                j = _skip_string(src, j)
                continue
            if c == "`":
                j = _skip_template(src, j)
                continue
            if c == "{" or c == "[":
                end = _match_brace(src, j) if c == "{" else _match_bracket(src, j)
                j = end if end > 0 else j + 1
                continue
            j += 1
        tail = src[j + 1 : j + 1 + 200]
        # Phase form: register(NS, "en", dict)
        single = re.match(r'\s*"(zh|en)"\s*,\s*', tail)
        if single:
            if single.group(1) != "en":
                continue
            after = j + 1 + single.end()
            while after < len(src) and src[after] in " \t\r\n":
                after += 1
            if after < len(src) and src[after] == "{":
                add(ns, parse_dict(_slice_brace(src, after)))
            else:
                ident = IDENT.match(src, after)
                if ident:
                    add(ns, parse_dict(object_by_ident(src, ident.group(0))))
            continue
        # Pair form: register(NS, { zh, en })
        k = j + 1
        while k < len(src) and src[k] in " \t\r\n":
            k += 1
        if k < len(src) and src[k] == "{":
            body = _slice_brace(src, k)
            if body:
                add(ns, resolve_en(src, body))
        if sum(len(v) for v in result.values()) == before_count:
            diagnostics.append(f"{path}: namespace {ns!r} registered but no en dictionary recovered")

    # Pair-loop form: `for ([locale, dict] of pairs) register(NS, locale, dict)`
    for loop in re.finditer(r"register\(\s*([\w$]+)\s*,\s*locale\s*,\s*dict\s*\)", src):
        # `loop.start(1)` is the namespace argument, not the call receiver.
        ns = namespace_at(loop.start(1))
        if ns is None:
            continue
        for pm in re.finditer(r'\[\s*"en"\s*,\s*\{', src):
            brace = src.index("{", pm.end() - 1)
            add(ns, parse_dict(_slice_brace(src, brace)))
    if diagnostics and os.environ.get("DSH_RU_I18N_DIAG"):
        diagnostics.insert(0, f"--- {path}")
        for line in diagnostics:
            print("  ? " + line, file=sys.stderr)
    return result


def package_of(path: str) -> str | None:
    """Nearest enclosing package.json name, walking up from the bundle."""
    d = os.path.dirname(path)
    while len(d) > 3:
        candidate = os.path.join(d, "package.json")
        if os.path.exists(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    return json.load(fh).get("name")
            except Exception:
                return None
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def bundle_paths(root: str) -> list[str]:
    """Every candidate client bundle under an install root or node_modules dir."""
    base = root if os.path.basename(root) == "node_modules" else os.path.join(root, "node_modules")
    patterns = [
        os.path.join(base, "@deepseek-ai/*/lib/client.js"),
        os.path.join(base, "@deepseek-ai/*/lib/client/index.js"),
        os.path.join(base, "*/lib/client.js"),
        os.path.join(base, "@*/*/lib/client.js"),
        os.path.join(base, "*/client/client.js"),
        os.path.join(base, "@*/*/client/client.js"),
    ]
    paths: list[str] = []
    for pattern in patterns:
        paths += glob.glob(pattern)
    return sorted(set(paths))


def harvest(paths: list[str], skip: tuple[str, ...] = ("dsh-ru", "russian-lang")) -> dict:
    """Scan bundles into `{namespaces, sources}`; one bad bundle never aborts."""
    namespaces: dict[str, dict[str, str]] = {}
    sources: dict[str, list[str]] = {}
    for path in paths:
        if any(marker in path for marker in skip):
            continue
        try:
            found = harvest_file(path)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  ! {path}: {exc}", file=sys.stderr)
            continue
        if not found:
            continue
        pkg = package_of(path)
        for ns, entries in found.items():
            namespaces.setdefault(ns, {}).update(entries)
            if pkg:
                sources.setdefault(ns, [])
                if pkg not in sources[ns]:
                    sources[ns].append(pkg)
    return {
        "namespaces": {ns: dict(sorted(v.items())) for ns, v in sorted(namespaces.items())},
        "sources": {ns: sorted(v) for ns, v in sorted(sources.items())},
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = sys.argv[1].rstrip("/\\")
    out_path = sys.argv[2] if len(sys.argv) > 2 else "en-dicts.json"
    paths = bundle_paths(root)
    payload = harvest(paths)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
    total = sum(len(v) for v in payload["namespaces"].values())
    print(f"{out_path}: {len(payload['namespaces'])} namespaces, {total} keys, {len(paths)} bundles scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
