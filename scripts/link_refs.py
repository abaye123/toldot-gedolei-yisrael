"""Link people mentioned in entries (teachers, students, family) to their own entries.

Usage:
    python scripts/link_refs.py [--dry-run]

For every person-valued claim it sets `"ref": "<person id>"` (an id from
data/people.json) when the mentioned person can be identified:
  1. Wikidata: the entry's Wikidata snapshot names the relative/teacher/student
     as an item (P22 father, P1066 student of, P802 student, ...), and that
     item is a person in the registry whose names match the claim.
  2. Registry: exactly one registry person has a matching name and an era
     compatible with this entry.
Anything else is left without `ref` and listed in data/review/refs-unresolved.csv.
Manual decisions: data/review/ref-overrides.json
    {"<entry id>|<field>|<claim value or family name>": "<person id>" | null}
Re-runnable: refs are recomputed every time (overrides win).
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import names  # noqa: E402
from resolve import eras_compatible  # noqa: E402
from sources import wikidata  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ROOT / "data" / "entries"
PEOPLE = ROOT / "data" / "people.json"
REVIEW = ROOT / "data" / "review"
OVERRIDES = REVIEW / "ref-overrides.json"

# Fields whose claims name a person, and the Wikidata properties that back them.
PERSON_FIELDS = {
    "teachers": ("student_of",),
    "students": ("student",),
    "family": ("father", "mother", "spouse", "child", "sibling"),
}
# Leading relation words in values like "אביו רבי מימון הדיין" / "בנו רבי אברהם".
RELATION_WORDS = re.compile(
    r"^(אביו|אמו|בנו|בניו|בתו|אחיו|אחותו|חמיו|חותנו|חתנו|גיסו|דודו|נכדו|אשתו|רעייתו|רבו|תלמידו|בן אחיו|בן אחותו)\s+")


def mentioned_name(text):
    """The person's name inside a claim value: no relation word, no description."""
    text = re.sub(r"\([^)]*\)", " ", names.fold(text))
    text = RELATION_WORDS.sub("", text.strip())
    text = re.split(r",|\s-\s|;|\sשמילא\s|\sבעל\s", text)[0]
    return text.strip()


def claim_texts(field, claim):
    value = claim["value"]
    if field == "family":
        return value["name"], [value["name"], value["relation"] + " " + value["name"]]
    return value, [value]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    people = json.loads(PEOPLE.read_text(encoding="utf-8"))
    by_qid = {p["links"]["wikidata"]: pid for pid, p in people.items() if p["links"].get("wikidata")}
    by_key, by_loose = {}, {}
    for pid, p in people.items():
        for k in names.keys(p["names"]):
            by_key.setdefault(k, set()).add(pid)
        for k in names.loose_keys(p["names"]):
            by_loose.setdefault(k, set()).add(pid)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}

    unresolved, stats = [], {"wikidata": 0, "registry": 0, "override": 0, "unresolved": 0}
    for path in sorted(ENTRIES.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        eid, era = entry["id"], entry["era"]["value"]
        wd_id = entry["sources"].get("wikidata", {}).get("id")
        wd_raw = wikidata.load(eid) if wd_id else None
        facts = wikidata.facts(wd_raw)["facts"] if wd_raw else {}
        changed = False
        for field, props in PERSON_FIELDS.items():
            linked_qids = {v["id"] for prop in props for v in facts.get(prop, []) if "id" in v}
            for claim in entry["fields"][field]:
                display, texts = claim_texts(field, claim)
                override_key = f"{eid}|{field}|{display}"
                key_set = names.keys([mentioned_name(t) for t in texts])
                ref, how = None, None
                if override_key in overrides:
                    ref, how = overrides[override_key], "override"
                else:
                    wd_hits = {by_qid[q] for q in linked_qids if q in by_qid
                               and key_set & names.keys(people[by_qid[q]]["names"])}
                    if len(wd_hits) == 1:
                        ref, how = wd_hits.pop(), "wikidata"
                    else:
                        reg_hits = {pid for k in key_set for pid in by_key.get(k, ())
                                    if pid != eid and eras_compatible(people[pid]["era"], era)}
                        if not reg_hits:  # spelling variants, e.g. a trailing "מפוניבז'"
                            loose = names.loose_keys([mentioned_name(t) for t in texts])
                            reg_hits = {pid for k in loose for pid in by_loose.get(k, ())
                                        if pid != eid and eras_compatible(people[pid]["era"], era)}
                        if len(reg_hits) == 1:
                            ref, how = reg_hits.pop(), "registry"
                        else:
                            unresolved.append([eid, field, display, mentioned_name(texts[0]),
                                               " | ".join(f"{p}: {people[p]['name']} ({people[p]['era']})"
                                                          for p in sorted(reg_hits)[:6])])
                if ref and how:
                    stats[how] += 1
                else:
                    stats["unresolved"] += 1
                if claim.get("ref") != ref:
                    changed = True
                    if ref:
                        claim["ref"] = ref
                    else:
                        claim.pop("ref", None)
        if changed and not args.dry_run:
            path.write_text(json.dumps(entry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    REVIEW.mkdir(parents=True, exist_ok=True)
    with open(REVIEW / "refs-unresolved.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["entry", "field", "value", "name_used", "candidates"])
        w.writerows(unresolved)
    print(f"refs: {stats}; unresolved -> data/review/refs-unresolved.csv")


if __name__ == "__main__":
    main()
