"""Build the writer's brief (data/briefs/<id>.md) from the raw snapshots.

Usage:
    python scripts/brief.py            rebuild all briefs listed in data/index.json
    python scripts/brief.py Q127398    rebuild one

Every section of the brief is labelled with its provider key, which the
writer copies into the `src` of each claim (see docs/data-model.md). The
brief also carries a ready-made `sources` registry for the entry.
Briefs are derived files: never edit them, rebuild them.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sources import hamichlol, mediawiki, seder_hadorot_segron, toldot_tannaim, wikidata, wikipedia  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "index.json"
BRIEFS = ROOT / "data" / "briefs"

# Article providers, in order of preference when more than one is present.
ARTICLE_ADAPTERS = [hamichlol, wikipedia]

# Upper bound on article text passed to the writers, to keep briefs focused.
MAX_TEXT_CHARS = 80000


def format_value(v):
    if "label" in v:
        return f"{v['label'] or '?'} ({v['id']})"
    if "year" in v:
        y = v["year"]
        if v["precision"] >= 11:
            s = v["raw"][1:11]
        else:
            s = str(abs(y)) + {8: " (decade)", 7: " (century)"}.get(v["precision"], "")
        if y < 0:
            s = f"{abs(y)} BCE"
        if v.get("calendar") == "Q1985786":
            s += " (Julian)"
        return s
    return v.get("text", "")


def names_for(title, wd, infobox):
    names = [title]
    if wd:
        names += [wd.get("label") or ""] + wd.get("aliases", [])
    for key, value in infobox:
        if key.startswith("כינוי") or key.startswith("שם"):
            names += [v.strip() for v in value.split(",")]
    return names


def build(eid, meta):
    registry, lines = {}, []
    articles = []
    for adapter in ARTICLE_ADAPTERS:
        page_meta, wikitext = adapter.load(eid)
        if page_meta:
            text, infobox = mediawiki.extract(wikitext)
            articles.append((adapter, page_meta, text, infobox))
            registry[adapter.NAME] = {
                "title": page_meta["title"], "url": page_meta["url"], "revid": page_meta["revid"],
                "retrieved": page_meta["retrieved"], "raw": page_meta["raw"], "credit": adapter.CREDIT,
            }
    wd_raw = wikidata.load(eid)
    wd = wikidata.facts(wd_raw) if wd_raw else None
    if wd_raw:
        registry["wikidata"] = {"id": eid, "url": wd_raw["url"], "retrieved": wd_raw["retrieved"],
                                "raw": wd_raw["raw"], "credit": wikidata.CREDIT}

    title = articles[0][1]["title"] if articles else meta["title"]
    infobox_all = [kv for a in articles for kv in a[3]]
    links = meta.get("links", {})
    all_rows = seder_hadorot_segron.load()
    # Rows linked by the registry are certain; name matches are only candidates.
    rows = [all_rows[n] for n in links.get("seder_hadorot_segron", [])]
    rows += [r for r in seder_hadorot_segron.match(names_for(title, wd, infobox_all)) if r not in rows]
    if rows:
        registry["seder_hadorot_segron"] = {"rows": ["<the n of each row you used>"], "url": seder_hadorot_segron.URL,
                                     "raw": seder_hadorot_segron.raw_rel(), "credit": seder_hadorot_segron.CREDIT}

    toldot = []
    if meta["era"] in toldot_tannaim.ERAS or links.get("toldot_tannaim"):
        page_titles = list(links.get("toldot_tannaim", []))
        page_titles += [t for t in toldot_tannaim.candidates(names_for(title, wd, infobox_all)) if t not in page_titles]
        for page_title in page_titles:
            page_meta, page_text = toldot_tannaim.load_by_title(page_title)
            if page_meta:
                toldot.append((page_meta, page_text))
    if toldot:
        registry["toldot_tannaim"] = {
            "pages": [{"title": m["title"], "url": m["url"], "revid": m["revid"], "raw": m["raw"]} for m, _ in toldot],
            "credit": toldot_tannaim.CREDIT,
        }

    lines += [f"# {title}", "", f"- id: {eid}", f"- era (requested): {meta['era']}"]
    if meta.get("article_missing"):
        lines.append(f"- NOTE: no article text available ({meta['article_missing']}); write from the other sources only")
    lines += [
        "",
        "## Sources registry",
        "",
        "Copy into the entry's `sources`, keeping only providers you actually cite.",
        "",
        "```json",
        json.dumps(registry, ensure_ascii=False, indent=1),
        "```",
    ]

    if wd:
        lines += ["", "## [src: wikidata] Wikidata facts", ""]
        if wd.get("description"):
            lines.append(f"- description: {wd['description']}")
        if wd.get("aliases"):
            lines.append(f"- aliases: {', '.join(wd['aliases'])}")
        for field, values in wd["facts"].items():
            lines.append(f"- {field}: {'; '.join(format_value(v) for v in values)}")

    if rows:
        lines += [
            "",
            "## [src: seder_hadorot_segron] Seder HaDorot candidate rows",
            "",
            "Rows marked [linked] were matched to this person by the registry; the others are matched by",
            "name only - use a row only if it clearly refers to this figure, and list its n in",
            "sources.seder_hadorot_segron.rows. Years are from Creation (traditional count); for people the two",
            "years are birth and death.",
            "",
        ]
        for r in rows:
            years = "-".join(f"{seder_hadorot_segron.year_label(y)} ({y})" for y in r["years"]) or "no year"
            linked = " [linked]" if r["n"] in links.get("seder_hadorot_segron", []) else ""
            lines.append(f"- n={r['n']}{linked} [{r['type'] or '?'}] {years}: {r['text']}")

    if toldot:
        lines += [
            "",
            "## [src: toldot_tannaim] Toldot Tannaim veAmoraim candidate pages",
            "",
            "Pages marked [linked] were matched to this person by the registry; others are matched by name",
            "only - use a page only if it clearly refers to this figure, and keep only the",
            "pages you used in sources.toldot_tannaim.pages.",
        ]
        for page_meta, page_text in toldot:
            if len(page_text) > toldot_tannaim.MAX_PAGE_CHARS:
                page_text = page_text[:toldot_tannaim.MAX_PAGE_CHARS] + "\n\n[...truncated]"
            linked = " [linked]" if page_meta["title"] in links.get("toldot_tannaim", []) else ""
            lines += ["", f"### Page{linked}: {page_meta['title']} (revision {page_meta['revid']})", "", page_text]

    for adapter, page_meta, text, infobox in articles:
        key = adapter.NAME
        if infobox:
            lines += ["", f"## [src: {key}] Infobox", ""]
            lines += [f"- {k}: {v}" for k, v in infobox]
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS] + "\n\n[...truncated]"
        lines += ["", f"## [src: {key}] Article text (revision {page_meta['revid']})", "",
                  text.replace("\n## ", "\n### ")]
    return "\n".join(lines) + "\n"


def write(eid, meta=None):
    meta = meta or json.loads(INDEX.read_text(encoding="utf-8"))[eid]
    BRIEFS.mkdir(parents=True, exist_ok=True)
    (BRIEFS / f"{eid}.md").write_text(build(eid, meta), encoding="utf-8")


def main():
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    ids = sys.argv[1:] or list(index)
    for eid in ids:
        write(eid, index[eid])
    print(f"{len(ids)} briefs written")


if __name__ == "__main__":
    main()
