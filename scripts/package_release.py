"""Build the assets of a GitHub release from the entries.

Usage:
    python scripts/package_release.py TAG [--out release]

Writes to the output folder:
    biographies.json       the whole bundle in one file (as dist/biographies.json)
    biographies-files.zip  the same content as separate files:
                             meta.json        format, author, license, eras,
                                              credits, and the entry ids in order
                             entries/<id>.json  one file per entry
                             schema/biography.schema.json
                             LICENSE, NOTICE, CREDITS.md
    SHA256SUMS             checksums of the two files above
    NOTES.md               the release description
"""

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

from build_site import ROOT, build_bundle

ZIP_EXTRAS = ["LICENSE", "NOTICE", "CREDITS.md", "schema/biography.schema.json"]


def dump(obj, indent=None):
    return json.dumps(obj, ensure_ascii=False, indent=indent) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag")
    ap.add_argument("--out", default="release")
    args = ap.parse_args()

    bundle = build_bundle(args.tag)
    entries = bundle["entries"]
    out = ROOT / args.out
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    (out / "biographies.json").write_text(dump(bundle, indent=1), encoding="utf-8", newline="\n")

    meta = {k: v for k, v in bundle.items() if k != "entries"}
    meta["entries"] = [e["id"] for e in entries]
    with zipfile.ZipFile(out / "biographies-files.zip", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("meta.json", dump(meta, indent=1))
        for e in entries:
            z.writestr(f"entries/{e['id']}.json", dump(e, indent=2))
        for name in ZIP_EXTRAS:
            z.write(ROOT / name, name)

    sums = "".join(
        f"{hashlib.sha256((out / n).read_bytes()).hexdigest()}  {n}\n"
        for n in ("biographies.json", "biographies-files.zip")
    )
    (out / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")

    by_era = {}
    for e in entries:
        by_era[e["era"]["value"]] = by_era.get(e["era"]["value"], 0) + 1
    era_lines = "".join(
        f"| {era['label']} | {by_era[era['key']]} |\n" for era in bundle["eras"] if era["key"] in by_era
    )
    notes = (
        f"{len(entries)} biographies, built {bundle['built']}.\n\n"
        "| תקופה | ערכים |\n|---|---|\n" + era_lines + "\n"
        "- `biographies.json` - the whole bundle in one file\n"
        "- `biographies-files.zip` - one JSON file per entry, `meta.json`, the schema, LICENSE, NOTICE, CREDITS.md\n"
        "- `SHA256SUMS` - checksums\n\n"
        "**Attribution is required:** any use of the biographies must credit **abaye** as their author, "
        "visibly to users (\"הביוגרפיות נערכו ע\"י abaye\"). License: AGPL-3.0 with an additional term (see NOTICE). "
        "The sources credited in each entry and in `credits` must be kept as well.\n"
    )
    (out / "NOTES.md").write_text(notes, encoding="utf-8", newline="\n")
    print(f"{len(entries)} entries -> {out}")


if __name__ == "__main__":
    main()
