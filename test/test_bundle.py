#!/usr/bin/env python3
"""Verify the shipped client bundle against the composed dictionary.

`lib/client.js` is a generated artifact, so the two things that can silently go
wrong are drift (the artifact no longer matches `build/ru.json`) and a bundle
the DSH page loader cannot consume. Both are checked here:

  1. regenerating from the dictionary reproduces the committed bytes,
  2. the inlined dictionary is exactly the composed one,
  3. Node can parse the bundle,
  4. executing the bundle against a stub module loader registers every
     namespace under `ru`, adds the language, and activates it.

Run: python3 test/test_bundle.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tools"))
import gen_dict_js  # noqa: E402

FAILURES: list[str] = []


def fail(message: str) -> None:
    FAILURES.append(message)


def main() -> int:
    dict_path = os.path.join(HERE, "build", "ru.json")
    bundle_path = os.path.join(HERE, "lib", "client.js")
    if not os.path.exists(dict_path):
        print("build/ru.json missing; run tools/build_ru.py first")
        return 1
    if not os.path.exists(bundle_path):
        print("lib/client.js missing; run tools/gen_dict_js.py first")
        return 1

    with open(dict_path, encoding="utf-8") as fh:
        expected = json.load(fh)["namespaces"]
    with open(bundle_path, encoding="utf-8") as fh:
        committed = fh.read()

    # 1. Deterministic regeneration: the artifact must be reproducible.
    with tempfile.TemporaryDirectory() as tmp:
        regenerated = os.path.join(tmp, "client.js")
        gen_dict_js.generate(
            dict_path, os.path.join(HERE, "lib", "client.template.js"), regenerated
        )
        with open(regenerated, encoding="utf-8") as fh:
            fresh = fh.read()
        if fresh != committed:
            fail("lib/client.js is stale: `python3 tools/gen_dict_js.py` changes it")

    # 2. The inlined literal must carry exactly the composed dictionary.
    marker = "const DICT = "
    start = committed.index(marker) + len(marker)
    depth, i = 0, start
    while i < len(committed):
        if committed[i] == "{":
            depth += 1
        elif committed[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    embedded = json.loads(committed[start : i + 1])
    if embedded != expected:
        fail("inlined dictionary differs from build/ru.json")

    # 3. The page loader evaluates the bundle as a script.
    node = shutil.which("node")
    if node is None:
        print("node not found; skipping bundle execution checks")
    else:
        syntax = subprocess.run(
            [node, "--check", bundle_path], capture_output=True, text=True
        )
        if syntax.returncode != 0:
            fail(f"node --check failed:\n{syntax.stderr}")
        else:
            # 4. Run the bundle with a stub loader and assert the registration
            #    contract the locale runtime expects.
            harness = os.path.join(HERE, "test", "run_bundle.mjs")
            run = subprocess.run(
                [node, harness, bundle_path, dict_path],
                capture_output=True,
                text=True,
            )
            if run.returncode != 0:
                fail(f"bundle execution failed:\n{run.stdout}\n{run.stderr}")
            elif run.stdout.strip() != "OK":
                fail(f"bundle execution reported: {run.stdout.strip()}")

            # 5. Upgrade path: a stale or malformed dictionary must still
            #    register and activate instead of breaking the interface.
            stale = os.path.join(HERE, "test", "run_bundle_stale.mjs")
            run = subprocess.run([node, stale, bundle_path], capture_output=True, text=True)
            if run.returncode != 0:
                fail(f"stale-dictionary run failed:\n{run.stdout}\n{run.stderr}")
            elif run.stdout.strip() != "OK":
                fail(f"stale-dictionary run reported: {run.stdout.strip()}")

    if FAILURES:
        print("FAIL\n" + "\n".join(FAILURES))
        return 1
    total = sum(len(v) for v in expected.values())
    print(f"bundle: OK ({len(expected)} namespaces, {total} keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
