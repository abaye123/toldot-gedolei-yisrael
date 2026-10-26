"""Compact bundle for applications that show the cards (e.g. Otzaria).

Usage:
    python scripts/app_bundle.py [--release TAG] [--out release/biographies-app.json.gz]

The full bundle carries per-claim provenance and review notes, which an
application does not show. This keeps what a card shows:
- every claim becomes its value; competing values are appended as
  "(או: ...)", as the viewer shows them;
- teachers, students and family keep `ref`, the id of the linked entry;
- `sources` lists, per entry, the credit key, a title and a link to the
  original page, so each card can credit its sources;
- empty fields are left out; review notes and raw snapshot paths are dropped.

Format `biographies-app`, version 1.
Top level: format, version, built, release, author, license, eras, credits,
entries. Entry: id, era, name, and optionally known_as, honorific,
generation, region, born / died ({hebrew, gregorian, place}), buried, roles,
teachers / students ([{name, ref?}]), family ([{relation, name, ref?}]),
works ([{title, description?}]), mentioned_in, summary, remember, sources
([{credit, title?, url}]).
"""

import argparse
import gzip
import json

from build_site import ROOT, build_bundle

APP_FORMAT = "biographies-app"
APP_VERSION = 1


def text(claim):
    if not claim:
        return None
    alts = [a["value"] for a in claim.get("alt", []) if a.get("value")]
    return claim["value"] + "".join(f" (או: {a})" for a in alts)


def person(claim, key="name"):
    out = {key: claim["value"]} if isinstance(claim["value"], str) else dict(claim["value"])
    if claim.get("ref"):
        out["ref"] = claim["ref"]
    return out


def life(event):
    out = {k: text(event.get(k)) for k in ("hebrew", "gregorian", "place")}
    return {k: v for k, v in out.items() if v} or None


def sources(entry):
    out = []
    for key, s in entry["sources"].items():
        credit = s.get("credit", key)
        if credit == "editorial":
            continue
        if s.get("pages"):
            for page in s["pages"]:
                out.append({"credit": credit, "title": page["title"].split("/")[-1], "url": page["url"]})
        elif s.get("url"):
            item = {"credit": credit, "url": s["url"]}
            if s.get("title"):
                item["title"] = s["title"]
            out.append(item)
    return out


def compact(entry):
    f = entry["fields"]
    out = {
        "id": entry["id"],
        "era": entry["era"]["value"],
        "name": text(f["name"]),
        "known_as": [c["value"] for c in f["known_as"]],
        "honorific": text(f["honorific"]),
        "generation": text(f["generation"]),
        "region": [c["value"] for c in f["region"]],
        "born": life(f["born"]),
        "died": life(f["died"]),
        "buried": text(f["buried"]),
        "roles": [c["value"] for c in f["roles"]],
        "teachers": [person(c) for c in f["teachers"]],
        "students": [person(c) for c in f["students"]],
        "family": [person(c) for c in f["family"]],
        "works": [{k: v for k, v in c["value"].items() if v} for c in f["works"]],
        "mentioned_in": text(f["mentioned_in"]),
        "summary": text(f["summary"]),
        "remember": text(f["remember"]),
        "sources": sources(entry),
    }
    return {k: v for k, v in out.items() if v not in (None, [], {})}


def build_app_bundle(release=None):
    bundle = build_bundle(release)
    out = {
        "format": APP_FORMAT,
        "version": APP_VERSION,
        "built": bundle["built"],
        "author": bundle["author"],
        "license": bundle["license"],
        "eras": bundle["eras"],
        "credits": bundle["credits"],
        "entries": [compact(e) for e in bundle["entries"]],
    }
    if release:
        out["release"] = release
    return out


def write_app_bundle(path, release=None):
    data = json.dumps(build_app_bundle(release), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # mtime=0 keeps the archive byte-identical for identical content.
    path.write_bytes(gzip.compress(data, compresslevel=9, mtime=0))
    return len(data)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", help="release tag recorded in the bundle")
    ap.add_argument("--out", default="release/biographies-app.json.gz")
    args = ap.parse_args()
    path = ROOT / args.out
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = write_app_bundle(path, args.release)
    print(f"{raw} bytes of JSON -> {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
