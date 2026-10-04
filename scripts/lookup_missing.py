"""Find Wikidata items for people that only a non-Wikidata source proposed.

Usage:
    python scripts/lookup_missing.py [--source seder_hadorot_segron] [--limit N]

The Wikidata candidate list (candidates.py) is built from occupations, so
sages whose item lacks a rabbinic occupation are missing from it (e.g. the
Radbaz). For every registry person created by the given source alone, this
searches Wikidata by name and accepts an item only if it is a human with a
Hebrew Wikipedia article, its name matches, and its death year is within
MAX_YEAR_GAP of the person's. Accepted items are written to
config/candidates-extra.json, which resolve.py reads as extra Wikidata
candidates; re-run resolve.py and scope.py afterwards.
"""

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import names  # noqa: E402
from resolve import MAX_YEAR_GAP  # noqa: E402
from sources.common import http_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
API = "https://www.wikidata.org/w/api.php"
EXTRA = ROOT / "config" / "candidates-extra.json"


def search(term):
    params = urllib.parse.urlencode({"action": "wbsearchentities", "search": term, "language": "he",
                                     "uselang": "he", "type": "item", "limit": 7, "format": "json"})
    return [r["id"] for r in http_json(f"{API}?{params}").get("search", [])]


def entities(ids):
    if not ids:
        return {}
    params = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(ids), "props": "claims|labels|aliases|sitelinks",
                                     "languages": "he", "sitefilter": "hewiki", "format": "json"})
    return http_json(f"{API}?{params}").get("entities", {})


def year(entity, pid):
    for claim in entity.get("claims", {}).get(pid, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
        t = value.get("time") if isinstance(value, dict) else None
        if t:
            return int(t[: t.index("-", 1)])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="seder_hadorot_segron")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--eras", default="geonim,rishonim,acharonim,acharonei_zmanenu",
                    help="only these eras (earlier figures rarely have dated Wikidata items)")
    args = ap.parse_args()

    people = json.loads((ROOT / "data" / "people.json").read_text(encoding="utf-8"))
    extra = json.loads(EXTRA.read_text(encoding="utf-8")) if EXTRA.exists() else {"entries": []}
    known = {e["id"] for e in extra["entries"]}
    eras = set(args.eras.split(","))
    todo = [p for p in people.values() if p["origin"] == args.source and not p["links"].get("wikidata")
            and p["era"] in eras]
    if args.limit:
        todo = todo[:args.limit]
    done_path = ROOT / "data" / "review" / "lookup-missing-done.json"  # resume support
    done = set(json.loads(done_path.read_text(encoding="utf-8"))) if done_path.exists() else set()
    todo = [p for p in todo if p["id"] not in done]
    print(f"{len(todo)} people to look up", flush=True)
    found = 0
    for n, p in enumerate(todo, 1):
        person_keys = names.keys(p["names"]) | names.loose_keys(p["names"])
        ids = []
        for term in sorted({n for n in p["names"] if names.key(n)}, key=len, reverse=True)[:2]:
            ids += [i for i in search(names.fold(term)) if i not in ids]
        best = None
        for qid, ent in entities(ids[:15]).items():
            humans = {c["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for c in ent.get("claims", {}).get("P31", [])}
            if "Q5" not in humans or "hewiki" not in ent.get("sitelinks", {}):
                continue
            item_names = [ent.get("labels", {}).get("he", {}).get("value", "")] + \
                         [a["value"] for a in ent.get("aliases", {}).get("he", [])] + [ent["sitelinks"]["hewiki"]["title"]]
            if not person_keys & (names.keys(item_names) | names.loose_keys(item_names)):
                continue
            died = year(ent, "P570")
            if p["died_ce"] is None or died is None or abs(died - p["died_ce"]) > MAX_YEAR_GAP:
                continue
            best = {"id": qid, "title": ent["sitelinks"]["hewiki"]["title"], "label": item_names[0] or None,
                    "era": p["era"], "born": year(ent, "P569"), "died": died, "description": None,
                    "found_for": p["id"]}
            break
        if best and best["id"] not in known:
            extra["entries"].append(best)
            known.add(best["id"])
            found += 1
            print(f"{p['id']} {p['name']} -> {best['id']} {best['title']}", flush=True)
            EXTRA.write_text(json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8")
        done.add(p["id"])
        done_path.write_text(json.dumps(sorted(done)), encoding="utf-8")
        if n % 10 == 0:
            print(f"  {n}/{len(todo)} looked up, {found} found", flush=True)
    EXTRA.write_text(json.dumps(extra, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{found} new Wikidata candidates from {len(todo)} people -> config/candidates-extra.json")


if __name__ == "__main__":
    main()
