"""Build the release bundle and the viewer from the entries.

Usage:
    python scripts/build_site.py

Writes:
    dist/biographies.json   entries (claims + provenance) + eras + credits registry
    site/index.html         searchable viewer with the bundle embedded
"""

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ROOT / "data" / "entries"
TEMPLATE = ROOT / "site" / "template.html"
CREDITS = json.loads((ROOT / "config" / "credits.json").read_text(encoding="utf-8"))

ERAS = [
    ("mikra", "תקופת המקרא"),
    ("zugot", "אנשי כנסת הגדולה והזוגות"),
    ("tannaim", "תנאים"),
    ("amoraim", "אמוראים"),
    ("savoraim", "סבוראים"),
    ("geonim", "גאונים"),
    ("rishonim", "ראשונים"),
    ("acharonim", "אחרונים"),
    ("acharonei_zmanenu", "אחרוני זמננו"),
]
ERA_ORDER = {k: i for i, (k, _) in enumerate(ERAS)}


def value(claim):
    return claim["value"] if claim else None


def sort_key(e):
    f = e["fields"]
    year = value(f["died"]["gregorian"]) or value(f["born"]["gregorian"]) or ""
    years = [int(y) for y in re.findall(r"\d{3,4}", year)]
    return ERA_ORDER.get(e["era"]["value"], 99), years[0] if years else 9999, value(f["name"]) or ""


def main():
    entries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ENTRIES.glob("*.json"))]
    entries.sort(key=sort_key)
    used = {s["credit"] for e in entries for s in e["sources"].values()}
    bundle = {
        "format": "biographies",
        "version": 2,
        "built": date.today().isoformat(),
        # Required by the additional term in NOTICE (AGPL-3.0 section 7(b)).
        "author": "abaye",
        "license": "AGPL-3.0 with an attribution term: any use of these biographies must credit abaye (see NOTICE)",
        "eras": [{"key": k, "label": label} for k, label in ERAS],
        "credits": {k: {key: v for key, v in CREDITS[k].items() if key != "note"} for k in sorted(used)},
        "entries": entries,
    }
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "biographies.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
    payload = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", payload)
    (ROOT / "site" / "index.html").write_text(html, encoding="utf-8")
    print(f"{len(entries)} entries -> dist/biographies.json, site/index.html")


if __name__ == "__main__":
    main()
