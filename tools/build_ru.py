#!/usr/bin/env python3
"""Compose the Russian dictionary for the DSH build installed on this machine.

Inputs (all under the repo):
    build/en-core.json      English dictionaries extracted from the platform bundles
    build/en-plugins.json   English dictionaries extracted from profile plugins
    vendor/ru/*.json        Russian translations carried over from dsh-russian-lang

Outputs:
    build/ru.json           the registry payload the plugin ships
    build/coverage.txt      per-namespace coverage report

Rules:
  * A Russian entry survives only when the current English inventory still has
    that key, so the shipped dictionary never accumulates dead weight.
  * A current English key with no Russian entry is reported as a gap. Gaps fall
    back to English at runtime, so a missing key degrades gracefully rather than
    breaking the interface.
  * Namespaces absent from the English inventory are dropped entirely.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(HERE, "build")
VENDOR = os.path.join(HERE, "vendor", "ru")
# Keys the locale runtime resolves without a dictionary entry of their own.
PLURAL_SUFFIX = re.compile(r"\.(?:one|few|many|other)$")

# Upstream renamed a namespace without changing its strings. The carried-over
# translations keep their original file, so the old id is folded into the new one
# at compose time (applied to Russian lookups only; English stays authoritative).
NAMESPACE_ALIASES = {
    "settings.subscriptions": "dsh-subscriptions",
}

# The carried-over corpus contains a handful of strings that were only half
# translated upstream (mixed Russian and English inside one value). Rather than
# editing the vendored files — which are refreshed from upstream — corrections
# live here and are applied last.
OVERRIDES_FILE = "overrides.json"


def load_english() -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for name in ("en-core.json", "en-plugins.json"):
        path = os.path.join(BUILD, name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for ns, entries in data.get("namespaces", {}).items():
            merged.setdefault(ns, {}).update(entries)
    return merged


def load_russian() -> dict[str, dict[str, str]]:
    """Merge every vendored Russian file, skipping malformed entries.

    `overrides.json` is applied last and wins. Non-string values are dropped:
    a literal null carried in from upstream must never reach the bundle.
    """
    merged: dict[str, dict[str, str]] = {}
    paths = sorted(glob.glob(os.path.join(VENDOR, "*.json")))
    paths.sort(key=lambda path: os.path.basename(path) == OVERRIDES_FILE)
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for ns, entries in data.items():
            if not isinstance(entries, dict):
                continue
            clean = {k: v for k, v in entries.items() if isinstance(v, str)}
            dropped = len(entries) - len(clean)
            if dropped:
                print(
                    f"  ! {os.path.basename(path)}: dropped {dropped} non-string value(s) in {ns}",
                    file=sys.stderr,
                )
            merged.setdefault(ns, {}).update(clean)
    return merged


def main() -> int:
    english = load_english()
    russian = load_russian()
    if not english:
        print("no English inventory found; run tools/extract_en.py first", file=sys.stderr)
        return 1

    shipped: dict[str, dict[str, str]] = {}
    report: list[str] = []
    total_kept = total_gap = total_stale = 0

    for ns in sorted(english):
        en = english[ns]
        ru = dict(russian.get(NAMESPACE_ALIASES.get(ns, ns), {}))
        ru.update(russian.get(ns, {}))
        # A plural family inherits coverage from its base key: `.one/.few/.many`
        # entries are extra templates, not separate UI strings.
        kept: dict[str, str] = {}
        for key, value in ru.items():
            base = PLURAL_SUFFIX.sub("", key)
            if key in en or base in en:
                kept[key] = value
        gaps = [k for k in en if k not in kept and k not in ru]
        stale = [k for k in ru if k not in kept]
        if kept:
            shipped[ns] = dict(sorted(kept.items()))
        total_kept += len(kept)
        total_gap += len(gaps)
        total_stale += len(stale)
        covered = len(en) - len(gaps)
        pct = (100.0 * covered / len(en)) if en else 100.0
        report.append(
            "%-26s %4d keys  %4d ru  %5.1f%%  gaps %-4d stale %d"
            % (ns, len(en), len(kept), pct, len(gaps), len(stale))
        )
        if gaps and os.environ.get("DSH_RU_SHOW_GAPS"):
            for key in gaps:
                report.append(f"      GAP {key!r} = {en[key]!r}")

    payload = {
        "namespaces": shipped,
        "meta": {
            "keys": total_kept,
            "namespaces": len(shipped),
            "gaps": total_gap,
            "staleDropped": total_stale,
        },
    }
    with open(os.path.join(BUILD, "ru.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
    with open(os.path.join(BUILD, "coverage.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(report) + "\n")

    print("\n".join(report))
    print(
        "\nshipped %d keys in %d namespaces; %d gaps, %d stale entries dropped"
        % (total_kept, len(shipped), total_gap, total_stale)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
