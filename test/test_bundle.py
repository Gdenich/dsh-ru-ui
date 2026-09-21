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


def extract_embedded(bundle: str) -> dict:
    """Recover the inlined dictionary literal from a rendered bundle."""
    marker = "const DICT = "
    start = bundle.index(marker) + len(marker)
    depth, i = 0, start
    while i < len(bundle):
        if bundle[i] == "{":
            depth += 1
        elif bundle[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    return json.loads(bundle[start : i + 1])


def main() -> int:
    bundle_path = os.path.join(HERE, "lib", "client.js")
    template_path = os.path.join(HERE, "lib", "client.template.js")
    composed_path = os.path.join(HERE, "build", "ru.json")
    if not os.path.exists(bundle_path):
        print("lib/client.js missing; run tools/gen_dict_js.py first")
        return 1

    with open(bundle_path, encoding="utf-8") as fh:
        committed = fh.read()
    with open(template_path, encoding="utf-8") as fh:
        template = fh.read()

    # The check must run in a fresh clone, where build/ does not exist: it is a
    # local artifact and is gitignored. So the bundle's own inlined dictionary is
    # the starting point, and the reproducibility claim is that re-rendering from
    # it reproduces the artifact byte for byte.
    embedded = extract_embedded(committed)

    # 1. Deterministic regeneration: the artifact must be reproducible.
    if gen_dict_js.render_bundle(embedded, template) != committed:
        fail("lib/client.js is stale: `python3 tools/gen_dict_js.py` changes it")

    # 2. Where the composed dictionary is available, it must be the same one.
    expected = embedded
    if os.path.exists(composed_path):
        with open(composed_path, encoding="utf-8") as fh:
            composed = gen_dict_js.unpack(json.load(fh))
        if composed != embedded:
            fail("inlined dictionary differs from build/ru.json")
        expected = composed
        with tempfile.TemporaryDirectory() as tmp:
            regenerated = os.path.join(tmp, "client.js")
            gen_dict_js.generate(composed_path, template_path, regenerated)
            with open(regenerated, encoding="utf-8") as fh:
                if fh.read() != committed:
                    fail("regenerating from build/ru.json does not reproduce the bundle")
    else:
        print("note: build/ru.json absent (fresh clone) — checking the bundle alone")
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
            with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8"
            ) as handle:
                json.dump({"namespaces": expected}, handle, ensure_ascii=False)
                dict_arg = handle.name
            run = subprocess.run(
                [node, harness, bundle_path, dict_arg],
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
