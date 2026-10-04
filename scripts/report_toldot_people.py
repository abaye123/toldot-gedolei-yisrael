"""Review report for the 'Toldot Tannaim veAmoraim' page index.

Refreshes the index when it is missing or outdated (index_entries does that;
a full refresh takes ~15 minutes of polite API calls), prints counts per page
kind and per era, and writes data/review/toldot_tannaim_pages.csv
(utf-8-sig, for opening in a spreadsheet). `length` is the plain-text length
of the page's transcluded section (or of its own text), not the wikitext size.

Usage:
    python scripts/report_toldot_people.py            use the saved index
    python scripts/report_toldot_people.py --refresh  re-download it first
"""

import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import toldot_tannaim  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "review" / "toldot_tannaim_pages.csv"


def main():
    if "--refresh" in sys.argv:
        toldot_tannaim.refresh_index()
    entries = toldot_tannaim.index_entries()

    kinds = Counter(e["kind"] for e in entries)
    print(f"{len(entries)} pages")
    for kind, n in kinds.most_common():
        print(f"  {kind:9} {n}")
    bios = [e for e in entries if e["kind"] == "bio"]
    print(f"bio pages by era ({len(bios)}):")
    for era, n in Counter(e["era"] for e in bios).most_common():
        print(f"  {era or '-':9} {n}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "kind", "era", "name", "aliases", "qualifier", "length", "title"])
        for e in entries:
            w.writerow([f"{toldot_tannaim.NAME}:{e['pageid']}", e["kind"], e["era"] or "", e["name"],
                        " | ".join(e["aliases"]), e["qualifier"] or "",
                        e.get("section_chars") or len(e.get("inline_text", "")), e["title"]])
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
