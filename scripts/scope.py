"""Second scope pass: Orthodox Torah figures only, from Wikipedia categories.

Usage:
    python scripts/scope.py

resolve.py already drops people whose Wikidata religion or Hebrew description
marks them as non-Orthodox. This pass reads the categories of the downloaded
Wikipedia articles and sets `scope` on every person in data/people.json:
    "ok"        in scope
    "excluded"  a category marks him as outside the scope (reason in scope_reason)
    "review"    Acharonim / Acharonei Zmanenu with no positive Orthodox signal:
                listed in data/review/scope-review.csv for a human decision
Decisions: data/review/scope-overrides.json  {"<person id>": "ok" | "excluded"}.
Only people with scope "ok" are selected for writing.
"""

import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import wikipedia  # noqa: E402
from sources.common import raw_path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = ROOT / "data" / "people.json"
REVIEW = ROOT / "data" / "review"
OVERRIDES = REVIEW / "scope-overrides.json"

CATEGORY = re.compile(r"\[\[\s*(?:קטגוריה|Category)\s*:\s*([^\]|]+)", re.I)
# Categories of people outside the scope. Note "שבתאות" (the topic) also
# tags opponents of Sabbateanism, so only "שבתאים" (the adherents) counts.
EXCLUDE = re.compile(r"^(רבנים|רבניות|מנהיגים|אנשי דת)\s+(רפורמ|קונסרבטיב|רקונסטרוקציוניסט|נאולוג|ליברל|פרוגרסיב)"
                     r"|^(שבתאים|פרנקיסטים|משיחי שקר|חכמים קראים|קראים|מומרים|יהודים שהתנצרו|יהודים שהתאסלמו)")
# Signals that a modern rabbi belongs to the Orthodox Torah world.
POSITIVE_CATEGORY = re.compile(r"אורתודוקס|חרדי|חסיד|אדמו\"ר|ראשי ישיב|פוסקי|דיינים|מקובלים|רבני .*ליטא|רבנים ליטאים"
                               r"|רבנים ספרדיים|ראשון לציון|רבנים ראשיים|בעלי תשובות|מחברי ספרי|מחברי ספרות תורנית"
                               r"|^תלמידי |בוגרי ישיבת|^אחרוני |רבנים: אחרונים|ראשוני האחרונים|רבני ערים|רבני מושבים"
                               r"|רבני מועצות|רבנים ביישוב|היישוב הישן|^פרשני |מהדירי ספרות תורנית|אגודת ישראל|דגל התורה"
                               r"|ש\"ס|פייטנים|רבני צנעא|רבני מרכז תימן|חכמי |רבני הציונות הדתית|נושאי כלים|שד\"רים"
                               r"|המזרחי|ישיבות ההסדר|רבנים: אחרונים")
# Rabbis of these communities are traditional unless a category says otherwise.
TRADITIONAL_COMMUNITY = re.compile(r"מרוקא|תוניס|תימני|תימן|עיראק|בבלי|סורי|חלב|דמשק|לוב|אלג'יר|פרס|כורדי|בוכר|ג'רב"
                                   r"|ספרדי|מצרי|תורכי|טורקי|יווני|בלקני|קווקז|גאורגי|הודי")
POSITIVE_DESCRIPTION = re.compile(r"ראש ישיבה|ראש ישיבת|אדמו\"ר|פוסק|דיין|מקובל|חסיד|חרדי|ליטאי|גאון|צדיק|מגיד|"
                                  r"רב העיר|רבה של|רב הקהילה|אב בית הדין|אב\"ד|משגיח|חכם|מחבר ספרי|מחכמי|מו\"ץ|"
                                  r"מורה צדק|ספרות תורנית|פרשן")
MODERN = {"acharonim", "acharonei_zmanenu"}


def main():
    people = json.loads(PEOPLE.read_text(encoding="utf-8"))
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    scope_path, _ = raw_path("wikidata", "_scope.json")
    descriptions = {q: v.get("description") or "" for q, v in
                    json.loads(scope_path.read_text(encoding="utf-8")).items()} if scope_path.exists() else {}
    counts, review = {}, []
    for pid, p in people.items():
        _, wikitext = wikipedia.load(pid)
        cats = [c.strip() for c in CATEGORY.findall(wikitext or "")]
        desc = descriptions.get(p["links"].get("wikidata"), "")
        bad = [c for c in cats if EXCLUDE.search(c)]
        if pid in overrides:
            scope, reason = overrides[pid], "override"
        elif bad:
            scope, reason = "excluded", f"category: {bad[0]}"
        elif p["era"] in MODERN and p["origin"] == "wikidata" and not (
                any(POSITIVE_CATEGORY.search(c) for c in cats) or POSITIVE_DESCRIPTION.search(desc)
                or (desc.startswith("רב") and TRADITIONAL_COMMUNITY.search(desc))
                or any(c.startswith("רבנים") and TRADITIONAL_COMMUNITY.search(c) for c in cats)):
            scope, reason = "review", "no Orthodox signal"
            review.append([pid, p["name"], p["era"], p["died_ce"] or "", desc, " | ".join(cats[:12])])
        else:
            scope, reason = "ok", ""
        p["scope"], p["scope_reason"] = scope, reason
        counts[scope] = counts.get(scope, 0) + 1
    PEOPLE.write_text(json.dumps(people, ensure_ascii=False, indent=1), encoding="utf-8")
    REVIEW.mkdir(parents=True, exist_ok=True)
    with open(REVIEW / "scope-review.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "era", "died_ce", "description", "categories"])
        w.writerows(review)
    excluded = [(pid, p["name"], p["scope_reason"]) for pid, p in people.items() if p["scope"] == "excluded"]
    print(f"scope: {counts}")
    for row in excluded[:40]:
        print("  excluded:", *row)
    print("review list -> data/review/scope-review.csv")


if __name__ == "__main__":
    main()
