"""Validate written entries: schema, provenance and style.

Usage:
    python scripts/validate.py              all entries in data/entries/
    python scripts/validate.py Q127398 ...  selected entries

Checks
- shape: a small built-in validator for the JSON Schema subset used in
  schema/biography.schema.json
- provenance: every claim's providers are registered in `sources`; every
  registered source is cited; raw snapshot files exist; credit keys exist;
  Seder HaDorot row numbers exist
- style: forbidden punctuation, academic phrasing, length limits
Exit code 1 if any entry has errors.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import seder_hadorot_segron  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "biography.schema.json").read_text(encoding="utf-8"))
CREDITS = json.loads((ROOT / "config" / "credits.json").read_text(encoding="utf-8"))
ENTRIES = ROOT / "data" / "entries"
INDEX_PATH = ROOT / "data" / "index.json"
INDEX = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {}
PEOPLE_PATH = ROOT / "data" / "people.json"
PEOPLE = json.loads(PEOPLE_PATH.read_text(encoding="utf-8")) if PEOPLE_PATH.exists() else {}

# Phrases that signal academic / secular framing (see docs/style-guide.md).
FORBIDDEN_PHRASES = ["לפנה\"ס", "לספירה", "חוקרים", "היסטוריונים", "על פי המחקר", "לפי המחקר", "אגדה", "מיתולוג",
                     "ביקורת המקרא", "נפטר בגיל", "דמות מקראית", "דמות היסטורית"]
FORBIDDEN_CHARS = {"–": "en dash", "—": "em dash"}
TYPE_MAP = {"string": str, "array": list, "object": dict, "null": type(None), "integer": int, "number": (int, float)}


def resolve(schema):
    ref = schema.get("$ref")
    if ref:
        node = SCHEMA
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return {**resolve(node), **{k: v for k, v in schema.items() if k != "$ref"}}
    return schema


def check(value, schema, path, errors):
    schema = resolve(schema)
    if "anyOf" in schema:
        trials = []
        for option in schema["anyOf"]:
            errs = []
            check(value, option, path, errs)
            if not errs:
                break
            trials.append(errs)
        else:
            errors.extend(min(trials, key=len))
        return
    types = schema.get("type")
    if types:
        types = types if isinstance(types, list) else [types]
        if not any(isinstance(value, TYPE_MAP[t]) and not (t == "integer" and isinstance(value, bool)) for t in types):
            errors.append(f"{path}: expected {types}, got {type(value).__name__}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{path}: too short")
    if isinstance(value, list):
        if len(value) > schema.get("maxItems", 10**9):
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        for i, item in enumerate(value):
            check(item, schema.get("items", {}), f"{path}[{i}]", errors)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}.{key}: missing")
        for key, item in value.items():
            if key in props:
                check(item, props[key], f"{path}.{key}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{key}: unexpected field")


def claims(node, path="fields"):
    """Yield (path, claim) for every claim (including alts) under `node`."""
    if isinstance(node, dict) and "src" in node and "value" in node:
        yield path, node
        for i, alt in enumerate(node.get("alt", [])):
            yield from claims(alt, f"{path}.alt[{i}]")
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from claims(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from claims(v, f"{path}[{i}]")


def texts(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from texts(v)


def provenance(entry, errors, warnings):
    registry = entry.get("sources", {})
    used = set()
    all_claims = list(claims(entry.get("fields", {}))) + [("era", entry.get("era", {}))]
    for path, claim in all_claims:
        if claim.get("ref") and PEOPLE and claim["ref"] not in PEOPLE:
            warnings.append(f"{path}: ref {claim['ref']!r} is not in data/people.json")
        for provider in claim.get("src", []):
            used.add(provider)
            if provider != "editorial" and provider not in registry:
                errors.append(f"{path}: cites '{provider}' which is not in sources")
    for provider, src in registry.items():
        if provider not in used:
            warnings.append(f"source '{provider}' is registered but never cited")
        if src.get("credit") not in CREDITS:
            errors.append(f"sources.{provider}: unknown credit key {src.get('credit')!r}")
        if src.get("raw") and not (ROOT / src["raw"]).exists():
            errors.append(f"sources.{provider}: raw file missing: {src['raw']}")
    for page in registry.get("toldot_tannaim", {}).get("pages", []):
        if not (ROOT / page["raw"]).exists():
            errors.append(f"sources.toldot_tannaim: raw file missing: {page['raw']}")
    rows = registry.get("seder_hadorot_segron", {}).get("rows", [])
    if rows:
        total = len(seder_hadorot_segron.load())
        for n in rows:
            if not isinstance(n, int) or not 0 <= n < total:
                errors.append(f"sources.seder_hadorot_segron.rows: bad row {n!r}")


def style(entry, errors, warnings):
    fields = entry.get("fields", {})
    text = "\n".join(t for _, c in claims(fields) for t in texts(c["value"]))
    for ch, label in FORBIDDEN_CHARS.items():
        if ch in text:
            errors.append(f"contains {label}")
    for phrase in FORBIDDEN_PHRASES:
        if phrase in text:
            warnings.append(f"academic/secular phrase: {phrase!r}")
    if re.search(r"[A-Za-z]{4,}", text):
        warnings.append("contains Latin-script words")
    summary = (fields.get("summary") or {}).get("value", "")
    if entry.get("review", {}).get("status") != "needs_rewrite" and not summary:
        errors.append("summary is empty")
    if len(summary.split()) > 110:
        warnings.append(f"summary is long ({len(summary.split())} words)")
    meta = INDEX.get(entry.get("id"))
    era = entry.get("era", {}).get("value")
    if meta and era != meta["era"]:
        warnings.append(f"era changed from {meta['era']} to {era}")


def validate(path):
    errors, warnings = [], []
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        return [f"invalid JSON: {err}"], []
    check(entry, SCHEMA, "$", errors)
    if entry.get("id") != path.stem:
        errors.append(f"id {entry.get('id')!r} does not match file name")
    if not errors:
        provenance(entry, errors, warnings)
        style(entry, errors, warnings)
    return errors, warnings


def main():
    paths = [ENTRIES / f"{a}.json" for a in sys.argv[1:]] or sorted(ENTRIES.glob("*.json"))
    bad = 0
    for path in paths:
        errors, warnings = validate(path)
        if errors or warnings:
            print(f"{path.stem}:")
            for e in errors:
                print(f"  ERROR {e}")
            for w in warnings:
                print(f"  warn  {w}")
        bad += bool(errors)
    missing = sorted(set(INDEX) - {p.stem for p in ENTRIES.glob("*.json")})
    print(f"\n{len(paths)} checked, {bad} with errors, {len(missing)} indexed but not written")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
