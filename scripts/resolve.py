"""Build the people registry: every sage from every source, merged by identity.

Usage:
    python scripts/resolve.py

Each source proposes people:
    wikidata        config/candidates-full.json (scripts/candidates.py) + Hebrew labels/aliases
    toldot_tannaim  biography pages of Toldot Tannaim veAmoraim
    seder_hadorot_segron   person rows of Seder HaDorot
Sources are merged in that order. A proposal is linked to an existing person
when their names match (scripts/names.py) and era and years agree; otherwise it
becomes a new person, whose id is derived from the proposing source:
    Q127398               Wikidata
    tta-<pageid>          Toldot Tannaim veAmoraim
    sh-<row>              Seder HaDorot
Ids never change once assigned (an id is not a statement about sources).

Ambiguous proposals are neither linked nor created; they are listed in
data/review/resolve-ambiguous.csv. Decisions go to data/review/overrides.json:
    {"<source key>": "<person id>" | "new" | "skip"}
e.g. {"seder_hadorot_segron:412": "Q127398", "toldot_tannaim:9981": "skip"}

Writes data/people.json and data/review/resolve-report.csv.
"""

import csv
import json
import re
import sys
import urllib.parse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import names  # noqa: E402
from sources.common import http_json, raw_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = ROOT / "data" / "people.json"
REVIEW = ROOT / "data" / "review"
OVERRIDES = REVIEW / "overrides.json"
ENTRIES = ROOT / "data" / "entries"

ERA_ORDER = ["mikra", "zugot", "tannaim", "amoraim", "savoraim", "geonim", "rishonim", "acharonim", "acharonei_zmanenu"]
# Sources whose items may describe the same person more than once (Seder
# HaDorot lists a sage in a birth/death row and again in a term-of-office row).
SAME_SOURCE_MERGE = {"seder_hadorot_segron"}

# Death years further apart than this (in years) mean different people.
MAX_YEAR_GAP = 40


def eras_compatible(a, b):
    if not a or not b:
        return True
    return abs(ERA_ORDER.index(a) - ERA_ORDER.index(b)) <= 1


def wikidata_names(qids):
    """Hebrew labels + aliases for many items, cached in data/raw/wikidata/_names.json."""
    path, _ = raw_path("wikidata", "_names.json")
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    todo = [q for q in qids if q not in cache]
    for i in range(0, len(todo), 50):
        params = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(todo[i:i + 50]),
                                         "props": "labels|aliases", "languages": "he", "format": "json"})
        for qid, ent in http_json(f"https://www.wikidata.org/w/api.php?{params}").get("entities", {}).items():
            label = ent.get("labels", {}).get("he", {}).get("value")
            cache[qid] = [label] * bool(label) + [a["value"] for a in ent.get("aliases", {}).get("he", [])]
        if i // 50 % 20 == 19:
            path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  wikidata names: {i + 50}/{len(todo)}", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache


# Scope: Orthodox Torah figures only. Excluded by Wikidata religion (P140)
# or by the Hebrew description; refined later from Wikipedia categories (scope.py).
NON_ORTHODOX_RELIGIONS = {
    "Q205644", "Q339284", "Q1133485", "Q332473",  # Conservative, Reconstructionist, Reform, Neolog
    "Q1841", "Q9592", "Q3333484", "Q6423963", "Q432",  # Christianity, Islam
    "Q5491116", "Q208398", "Q189204", "Q10312696",  # Frankism, Karaism, Essenes, secular Judaism
}
_W = r"(?<![א-ת]){}(?![א-ת])"
NON_ORTHODOX_DESCRIPTION = re.compile("|".join(
    [_W.format(w) for w in ("רפורמי[תםן]?", "ה?רפורמית", "קונסרבטיבי[תםן]?", "ה?קונסרבטיבית", "ליברלי[תם]?",
                            "נאולוגי[תם]?", "קראי[תם]?", "נוצרי[תם]?", "מומר", "חילוני")]
    + ["רקונסטרוקציוני", "רקונסטרוקטיב", "המיר את דתו", "התנצר", "משיח שקר", "משיחי השקר",
       "התנועה השבתאית", "פרנקיסט", "פרוגרסיבי", "הומניסטי"]))


def scope_exclusion(qid, scope_data):
    info = scope_data.get(qid)
    if not info:
        return None
    if set(info["religion"]) & NON_ORTHODOX_RELIGIONS:
        return "religion"
    m = NON_ORTHODOX_DESCRIPTION.search(info.get("description") or "")
    return f"description: {m.group(0)}" if m else None


def wikidata_proposals():
    cand_path = ROOT / "config" / "candidates-full.json"
    index_path = ROOT / "data" / "index.json"
    cands = json.loads(cand_path.read_text(encoding="utf-8"))["entries"] if cand_path.exists() else []
    extra_path = ROOT / "config" / "candidates-extra.json"  # from lookup_missing.py
    if extra_path.exists():
        cands += json.loads(extra_path.read_text(encoding="utf-8"))["entries"]
    by_id = {c["id"]: c for c in cands}
    # People already selected for production are always part of the registry.
    if index_path.exists():
        for qid, meta in json.loads(index_path.read_text(encoding="utf-8")).items():
            if qid.startswith("Q") and qid not in by_id:
                by_id[qid] = {"id": qid, "title": meta["title"], "era": meta["era"], "born": None, "died": None}
    extra = wikidata_names(list(by_id))
    scope_path, _ = raw_path("wikidata", "_scope.json")
    scope_data = json.loads(scope_path.read_text(encoding="utf-8")) if scope_path.exists() else {}
    for c in by_id.values():
        yield {
            "exclude": scope_exclusion(c["id"], scope_data),
            "key": f"wikidata:{c['id']}", "source": "wikidata", "id": c["id"],
            "name": c.get("label") or c["title"], "aliases": [c["title"]] + extra.get(c["id"], []),
            "era": c.get("era"), "died_ce": c.get("died"), "born_ce": c.get("born"),
            "links": {"wikidata": c["id"], "wikipedia": c["title"]},
        }


def toldot_proposals():
    try:
        from sources import toldot_tannaim
        people = toldot_tannaim.people()
    except (ImportError, AttributeError) as err:
        print(f"  toldot_tannaim: not available ({err})")
        return
    for p in people:
        yield {"key": p["key"], "source": "toldot_tannaim", "id": f"tta-{p['pageid']}",
               "name": p["name"], "aliases": p.get("aliases", []), "era": p.get("era"),
               "died_ce": None, "born_ce": None, "links": {"toldot_tannaim": [p["title"]]}}


def seder_proposals():
    try:
        from sources import seder_hadorot_segron_people
        people = seder_hadorot_segron_people.people()
    except (ImportError, AttributeError) as err:
        print(f"  seder_hadorot_segron: not available ({err})")
        return
    from sources import seder_hadorot_segron
    rows = seder_hadorot_segron.load()
    for p in people:
        died = names.creation_to_ce(p["died"]) if p.get("died") else None
        born = names.creation_to_ce(p["born"]) if p.get("born") else None
        aliases = list(p.get("aliases", []))
        # 'רבי יוסף באב"ד': an acronym right after a first name is often the family name.
        aliases += [f"{p['name']} {a}" for a in p.get("aliases", []) if '"' in a and " " not in a.strip()]
        yield {"key": p["key"], "source": "seder_hadorot_segron", "id": f"sh-{p['key'].split(':', 1)[1]}",
               "name": p["name"], "aliases": aliases, "era": p.get("era"),
               "died_ce": died, "born_ce": born, "links": {"seder_hadorot_segron": [p["n"]]},
               "row_type": rows[p["n"]]["type"]}


class Registry:
    def __init__(self, previous):
        self.people = {}
        self.by_key = defaultdict(set)
        self.by_loose = defaultdict(set)
        # The key that created each person last time -> its id, so ids survive
        # re-runs. Only the creating key may claim an id: a key that was merely
        # linked to a person must never inherit (and overwrite) that person.
        self.previous = {p["origin_key"]: pid for pid, p in previous.items() if p.get("origin_key")}

    def add(self, prop):
        pid = self.previous.get(prop["key"], prop["id"])
        if pid in self.people:
            raise ValueError(f"id collision: {pid} for {prop['key']}")
        person = {
            "id": pid, "origin": prop["source"], "origin_key": prop["key"], "era": prop["era"], "name": prop["name"],
            "names": sorted(set([prop["name"]] + prop["aliases"])), "born_ce": prop["born_ce"],
            "died_ce": prop["died_ce"], "links": {}, "source_keys": [],
        }
        self.people[pid] = person
        self.link(pid, prop)
        return pid

    def link(self, pid, prop):
        person = self.people[pid]
        for provider, value in prop["links"].items():
            if isinstance(value, list):
                person["links"].setdefault(provider, [])
                person["links"][provider] += [v for v in value if v not in person["links"][provider]]
            else:
                person["links"].setdefault(provider, value)
        person["source_keys"].append(prop["key"])
        person["names"] = sorted(set(person["names"]) | {prop["name"], *prop["aliases"]})
        person["era"] = person["era"] or prop["era"]
        person["died_ce"] = person["died_ce"] or prop["died_ce"]
        person["born_ce"] = person["born_ce"] or prop["born_ce"]
        for k in names.keys([prop["name"], *prop["aliases"]]):
            self.by_key[k].add(pid)
        for k in names.loose_keys([prop["name"], *prop["aliases"]]):
            self.by_loose[k].add(pid)

    def candidates(self, prop):
        strict = self._candidates(prop, loose=False)
        if strict:
            return strict
        # Spelling variants: accept only with corroboration (same era and close years).
        return [c for c in self._candidates(prop, loose=True) if c[0][1] and c[0][2]]

    def _candidates(self, prop, loose):
        all_names = [prop["name"], *prop["aliases"]]
        prop_keys = names.loose_keys(all_names) if loose else names.keys(all_names)
        index = self.by_loose if loose else self.by_key
        scored = []
        for pid in {pid for k in prop_keys for pid in index.get(k, ())}:
            p = self.people[pid]
            if prop["source"] in {k.split(":")[0] for k in p["source_keys"]} and prop["source"] not in SAME_SOURCE_MERGE:
                continue  # two items of the same source are different people
            if not eras_compatible(p["era"], prop["era"]):
                continue
            if p["died_ce"] and prop["died_ce"] and abs(p["died_ce"] - prop["died_ce"]) > MAX_YEAR_GAP:
                continue
            shared = prop_keys & (names.loose_keys(p["names"]) if loose else names.keys(p["names"]))
            primary = (names.loose_key(prop["name"]) if loose else names.key(prop["name"])) in shared
            same_era = bool(p["era"]) and p["era"] == prop["era"]
            years_agree = bool(p["died_ce"] and prop["died_ce"])
            scored.append(((primary, years_agree, same_era, len(shared)), pid))
        scored.sort(reverse=True)
        return scored


def main():
    previous = json.loads(PEOPLE.read_text(encoding="utf-8")) if PEOPLE.exists() else {}
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    enabled = {k for k, v in json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8")).items()
               if v.get("enabled")}
    exclude = json.loads((ROOT / "config" / "exclude.json").read_text(encoding="utf-8"))
    reg = Registry(previous)
    report, ambiguous = [], []

    for source, proposals in (("wikidata", wikidata_proposals()), ("toldot_tannaim", toldot_proposals()),
                              ("seder_hadorot_segron", seder_proposals())):
        if source not in enabled:
            print(f"{source}: disabled in config/sources.json")
            continue
        counts = defaultdict(int)
        for prop in proposals:
            decision = overrides.get(prop["key"])
            if prop["key"] in exclude["keys"] or prop.get("row_type") in exclude.get("seder_hadorot_segron_types", []):
                decision = "skip"
            if prop.get("exclude") and decision not in ("new",):
                action, target = f"excluded ({prop['exclude']})", ""
            elif decision == "skip":
                action, target = "skipped", ""
            elif decision == "new" or source == "wikidata":
                action, target = "new", reg.add(prop)
            elif decision:
                reg.link(decision, prop)
                action, target = "linked (override)", decision
            else:
                cands = reg.candidates(prop)
                if not cands:
                    action, target = "new", reg.add(prop)
                elif len(cands) == 1 or cands[0][0] > cands[1][0]:
                    reg.link(cands[0][1], prop)
                    action, target = "linked", cands[0][1]
                else:
                    action, target = "ambiguous", ""
                    ambiguous.append([prop["key"], prop["name"], prop["era"] or "", prop["died_ce"] or "",
                                      " | ".join(f"{pid}: {reg.people[pid]['name']} ({reg.people[pid]['era']}, "
                                                 f"{reg.people[pid]['died_ce']})" for _, pid in cands[:5])])
            counts[action] += 1
            report.append([prop["key"], action, target, prop["name"], prop["era"] or ""])
        print(f"{source}: {dict(counts)}", flush=True)

    REVIEW.mkdir(parents=True, exist_ok=True)
    PEOPLE.write_text(json.dumps(reg.people, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(REVIEW / "resolve-report.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_key", "action", "person_id", "name", "era"])
        w.writerows(report)
    with open(REVIEW / "resolve-ambiguous.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source_key", "name", "era", "died_ce", "candidates"])
        w.writerows(ambiguous)
    multi = sum(1 for p in reg.people.values() if len(p["source_keys"]) > 1)
    print(f"\n{len(reg.people)} people ({multi} from more than one source); "
          f"{len(ambiguous)} ambiguous -> data/review/resolve-ambiguous.csv")


if __name__ == "__main__":
    main()
