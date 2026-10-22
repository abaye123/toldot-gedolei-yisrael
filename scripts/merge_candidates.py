"""Collect possible duplicate people for the owner's review, from the writing-run
notes and from entry flags, into data/review/merge-candidates.csv.

kind: both_written (two cards, maybe one person: decide and fill decision/keep_id),
one_written (a skipped id that duplicates a card: link it in overrides.json),
none_written. Rerun at any time; it overwrites the CSV.

    python scripts/merge_candidates.py
"""
import csv, glob, json, os, re
ID = r"(?:Q\d+|sh-\d+b?|tta-\d+)"
people = json.load(open("data/people.json", encoding="utf-8"))
has = lambda i: os.path.exists(f"data/entries/{i}.json")
name = lambda i: (people.get(i) or {}).get("name", "")
pairs = {}
def add(a, b, why, where):
    if a == b or a not in people or b not in people:
        return
    k = tuple(sorted((a, b)))
    pairs.setdefault(k, []).append((why, where))
# notes: "a = b", "a/b" after merge words, "a maybe = b", "a vs b", "a -> b"
for line in open("data/review/writing-run-notes.md", encoding="utf-8"):
    batch = (re.search(r"batch \S+", line) or re.search(r"^- \S+", line) or [""])[0]
    for m in re.finditer(rf"({ID})\s*(?:=|maybe =|may be =|probably =|vs|/)\s*({ID})", line):
        ctx = line[max(0, m.start() - 40):m.end() + 10].strip()
        if "/" in m.group(0) and not re.search(r"[Mm]erge|same|maybe|possibl", line):
            continue  # "a/b" lists alternatives, not a merge
        add(m.group(1), m.group(2), ctx, "notes")
    for m in re.finditer(rf"({ID})[^;.]{{0,60}}?(?:same person as|possible merge with|may be the same as|may be)\s*({ID})", line):
        add(m.group(1), m.group(2), line[m.start():m.end()].strip(), "notes")
# entry flags that name another id with merge wording
merge_words = re.compile(r"אותו אדם|אותו חכם|איחוד|מיזוג|לאחד|כפיל|זהה|זהות|merge|same person|ייתכן שהוא|אפשר שהוא|קרוב לומר")
for f in glob.glob("data/entries/*.json"):
    me = os.path.basename(f)[:-5]
    d = json.load(open(f, encoding="utf-8"))
    for fl in d.get("review", {}).get("flags", []):
        if merge_words.search(fl):
            for other in re.findall(ID, fl):
                add(me, other, fl[:200], "flag")
rows = []
for (a, b), why in pairs.items():
    kind = "both_written" if has(a) and has(b) else "one_written" if has(a) or has(b) else "none_written"
    rows.append([kind, a, name(a), "yes" if has(a) else "no", b, name(b), "yes" if has(b) else "no",
                 " | ".join(sorted({w for w, _ in why}))[:400], "", ""])
order = {"both_written": 0, "one_written": 1, "none_written": 2}
rows.sort(key=lambda r: (order[r[0]], r[1]))
with open("data/review/merge-candidates.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["kind", "id_a", "name_a", "entry_a", "id_b", "name_b", "entry_b", "evidence", "decision", "keep_id"])
    w.writerows(rows)
from collections import Counter
print(len(rows), Counter(r[0] for r in rows))
