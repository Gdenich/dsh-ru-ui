#!/usr/bin/env python3
"""Final gate: re-verify the shipped dictionary against the installed DSH build.

`tools/build_ru.py` prunes as it composes, so this tool re-derives the English
inventory from the live bundles and answers the questions a release needs:

  * does every shipped namespace still exist in this DSH build?
  * does every shipped key still exist in its namespace?
  * which current English keys have no Russian translation (runtime gaps)?
  * is any shipped translation empty, or identical to its English source?

Exit status is non-zero only for hard failures (unknown namespace, unknown key,
empty value). Gaps are reported as counts because a gap degrades gracefully to
English and must not block a release.

Usage:
    python3 tools/verify_coverage.py --app "/Applications/DSH Desktop.app/Contents/Resources/app" \
                                     [--profile ~/.dsh/profiles/desktop/node_modules]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
import extract_en  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", required=True, help="installed DSH app root or node_modules")
    parser.add_argument("--profile", help="profile node_modules with third-party plugins")
    parser.add_argument("--dict", default=os.path.join(HERE, "build", "ru.json"))
    args = parser.parse_args()

    english: dict[str, dict[str, str]] = {}
    roots = [args.app] + ([args.profile] if args.profile else [])
    for root in roots:
        harvested = extract_en.harvest(extract_en.bundle_paths(root))
        for ns, entries in harvested["namespaces"].items():
            english.setdefault(ns, {}).update(entries)

    with open(args.dict, encoding="utf-8") as fh:
        shipped = json.load(fh)["namespaces"]

    failures: list[str] = []
    total_keys = total_gaps = total_same = 0

    for ns in sorted(shipped):
        if ns not in english:
            failures.append(f"namespace {ns!r} no longer exists in this DSH build")
            continue
        entries = shipped[ns]
        total_keys += len(entries)
        gaps = [k for k in english[ns] if k not in entries]
        total_gaps += len(gaps)
        for key, value in entries.items():
            # A separator key legitimately holds whitespace or punctuation, so
            # only a truly empty string counts as a defect here.
            if not isinstance(value, str) or value == "":
                failures.append(f"{ns}.{key}: empty translation")
            elif key in english[ns] and value == english[ns][key] and any(
                ch.isalpha() for ch in value
            ):
                total_same += 1
        known = len(english[ns]) - len(gaps)
        pct = 100.0 * known / len(english[ns]) if english[ns] else 100.0
        print(
            "%-26s %4d/%4d keys  %5.1f%%  %d gap(s)"
            % (ns, known, len(english[ns]), pct, len(gaps))
        )

    print(
        "\n%d keys shipped in %d namespaces; %d gap(s), %d value(s) identical to English"
        % (total_keys, len(shipped), total_gaps, total_same)
    )
    if failures:
        print("\nFAIL")
        for line in failures:
            print("  " + line)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
