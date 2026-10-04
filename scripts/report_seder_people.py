"""Review report for the people extracted from Seder HaDorot.

Prints the number of people per era and writes
data/review/seder_hadorot_segron_people.csv (UTF-8 with BOM, opens in Excel).

Usage:
    python scripts/report_seder_people.py
"""

import csv
from collections import Counter
from pathlib import Path

from sources.seder_hadorot_segron_people import ERA_BOUNDS, LAST_ERA, people

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "review" / "seder_hadorot_segron_people.csv"
COLUMNS = ["key", "era", "born", "died", "name", "aliases", "works", "text"]


def main():
    found = people()
    counts = Counter(p["era"] for p in found)
    order = [era for era, _ in ERA_BOUNDS] + [LAST_ERA, None]
    print(f"{len(found)} people")
    for era in order:
        print(f"  {era or '(none)':<20} {counts.get(era, 0)}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for p in found:
            writer.writerow([p["key"], p["era"] or "", p["born"] or "", p["died"] or "", p["name"],
                             " | ".join(p["aliases"]), " | ".join(p["works"]), p["text"]])
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
