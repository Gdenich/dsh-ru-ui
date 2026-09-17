#!/usr/bin/env python3
"""Report shipped translations that are still identical to their English source.

A value equal to the English source is usually an untranslated leak, but plenty
of legitimate cases exist: product names (JSON, HTML, Univer Office), example
values users type (http://localhost:7890), format templates ({value}M) and
protocol names (HTTP). This tool lists them so a reviewer can tell the two apart
instead of trusting a raw percentage.

Usage:
    python3 tools/audit_english.py [build/ru.json] [build/en-core.json ...]
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Values that are not prose: identifiers, templates, URLs, protocol names.
NOT_PROSE = re.compile(r"^[^A-Za-zА-Яа-яЁё]*$|^\{[^}]*\}$|^https?://|^[A-Z0-9.+_-]{1,12}$")


def main() -> int:
    dict_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "build", "ru.json")
    en_paths = sys.argv[2:] or [
        os.path.join(HERE, "build", "en-core.json"),
        os.path.join(HERE, "build", "en-plugins.json"),
    ]
    english: dict[str, dict[str, str]] = {}
    for path in en_paths:
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for ns, entries in json.load(fh)["namespaces"].items():
                english.setdefault(ns, {}).update(entries)

    with open(dict_path, encoding="utf-8") as fh:
        shipped = json.load(fh)["namespaces"]

    leaks: list[tuple[str, str, str]] = []
    for ns, entries in shipped.items():
        source = english.get(ns, {})
        for key, value in entries.items():
            if source.get(key) != value:
                continue
            if NOT_PROSE.match(value):
                continue
            leaks.append((ns, key, value))

    for ns, key, value in leaks:
        print(f"{ns}.{key} = {value!r}")
    print(f"\n{len(leaks)} value(s) identical to English and not obviously a name or template")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
