"""Fetch raw snapshots for every entry in a candidate list.

Usage:
    python scripts/fetch.py config/pilot.json [--source wikipedia] [--force] [--retry-missing]

For each candidate it saves (see docs/data-model.md):
    data/raw/<source>/<id>.wikitext + .meta.json   the article, pinned to a revision
    data/raw/wikidata/<id>.json                    structured facts
and records the entry in data/index.json, then rebuilds its brief.

When the article cannot be fetched (e.g. blocked by a content filter) but a
Wikidata id is known, the entry is still created from Wikidata alone and
marked `article_missing`; `--retry-missing` refetches only those.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brief  # noqa: E402
from sources import hamichlol, mediawiki, toldot_tannaim, wikidata, wikipedia  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "data" / "index.json"
ADAPTERS = {"wikipedia": wikipedia, "hamichlol": hamichlol}

# Candidates per round trip (one article request + one Wikidata request).
BATCH = 50


def load_index():
    return json.loads(INDEX.read_text(encoding="utf-8")) if INDEX.exists() else {}


def save_index(index):
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")


def fetch_toldot(eid, entry, meta, wikitext, wd_raw):
    """Download the Toldot Tannaim veAmoraim pages that may match this sage."""
    if entry["era"] not in toldot_tannaim.ERAS:
        return
    infobox = mediawiki.extract(wikitext)[1] if wikitext else []
    names = brief.names_for(entry["title"], wikidata.facts(wd_raw), infobox)
    try:
        toldot_tannaim.ensure(toldot_tannaim.candidates(names))
    except Exception as err:  # optional source; never block the main fetch
        print(f"  toldot_tannaim: {err}", flush=True)


def backfill_toldot(index):
    for eid, entry in index.items():
        meta, wikitext = wikipedia.load(eid)
        fetch_toldot(eid, entry, meta, wikitext, wikidata.load(eid))
        brief.write(eid, entry)


def select_people(spec):
    """Pick people from data/people.json: a JSON file with a list of ids, or
    filters like 'era=tannaim,origin=toldot_tannaim,limit=5'."""
    people = json.loads((ROOT / "data" / "people.json").read_text(encoding="utf-8"))
    if spec == "all":
        return list(people.values())
    if spec.endswith(".json") and Path(spec).exists():
        return [people[i] for i in json.loads(Path(spec).read_text(encoding="utf-8"))]
    filters = dict(part.split("=", 1) for part in spec.split(",") if part)
    limit = int(filters.pop("limit", 0)) or None
    chosen = [p for p in people.values() if all(str(p.get(k)) == v for k, v in filters.items())]
    return chosen[:limit]


def fetch_registry(spec, force=False):
    """Fetch everything the selected people link to, and index them.

    Works in chunks of BATCH people: each chunk is fetched and saved before the
    next starts, so progress is visible and an interrupted run resumes where it
    stopped (people already in the index with their snapshots are skipped).
    """
    index = load_index()
    chosen = select_people(spec)
    sync_index(index, chosen, prune=(spec == "all"))
    if not force:
        chosen = [p for p in chosen if not (p["id"] in index and _snapshots_present(p))]
    print(f"{len(chosen)} people to fetch", flush=True)
    for start in range(0, len(chosen), BATCH):
        chunk = chosen[start:start + BATCH]
        titles = [p["links"]["wikipedia"] for p in chunk if p["links"].get("wikipedia")]
        qids = [p["links"]["wikidata"] for p in chunk if p["links"].get("wikidata")]
        pages = wikipedia.fetch_many(titles) if titles else {}
        wd = wikidata.fetch_many(qids) if qids else {}
        for p in chunk:
            pid, links = p["id"], p["links"]
            entry = {"era": p["era"], "requested_title": links.get("wikipedia") or p["name"], "title": p["name"],
                     "links": {k: v for k, v in links.items() if k in ("toldot_tannaim", "seder_hadorot_segron")}}
            result = pages.get(links.get("wikipedia"))
            if isinstance(result, tuple) and not result[0]["disambiguation"]:
                wikipedia.save(pid, *result)
                entry["title"] = result[0]["title"]
            elif links.get("wikipedia"):
                entry["article_missing"] = str(result)
            if links.get("wikidata") in wd:
                wikidata.save(pid, wd[links["wikidata"]])
            if links.get("toldot_tannaim"):
                toldot_tannaim.ensure(links["toldot_tannaim"])
            index[pid] = entry
            brief.write(pid, entry)
        save_index(index)
        print(f"{min(start + BATCH, len(chosen))}/{len(chosen)} done", flush=True)


def sync_index(index, chosen, prune):
    """Bring indexed people in line with the registry (era, links); with
    `prune`, drop indexed ids the registry no longer has (merged away)."""
    people = json.loads((ROOT / "data" / "people.json").read_text(encoding="utf-8"))
    changed = []
    for p in chosen:
        entry = index.get(p["id"])
        if not entry:
            continue
        links = {k: v for k, v in p["links"].items() if k in ("toldot_tannaim", "seder_hadorot_segron")}
        if entry.get("links") != links or entry.get("era") != p["era"]:
            entry["links"], entry["era"] = links, p["era"]
            changed.append(p["id"])
    if prune:
        for pid in [pid for pid in index if pid not in people]:
            del index[pid]
            (ROOT / "data" / "briefs" / f"{pid}.md").unlink(missing_ok=True)
            print(f"dropped {pid} (no longer in the registry)", flush=True)
    for pid in changed:
        brief.write(pid, index[pid])
    save_index(index)
    if changed:
        print(f"{len(changed)} indexed people updated from the registry", flush=True)


def _snapshots_present(person):
    links = person["links"]
    if links.get("wikipedia") and wikipedia.load(person["id"])[0] is None:
        return False
    if links.get("wikidata") and wikidata.load(person["id"]) is None:
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates", nargs="?", help="candidate list (JSON); omit with --people")
    ap.add_argument("--people", help="select from data/people.json: 'all', an ids .json file, or filters 'era=..,origin=..,limit=N'")
    ap.add_argument("--source", default="wikipedia", choices=ADAPTERS)
    ap.add_argument("--force", action="store_true", help="refetch everything")
    ap.add_argument("--retry-missing", action="store_true", help="refetch only entries whose article is missing")
    ap.add_argument("--backfill-toldot", action="store_true",
                    help="only fetch Toldot Tannaim veAmoraim pages for already indexed entries")
    args = ap.parse_args()
    if args.people:
        fetch_registry(args.people, force=args.force)
        return
    if args.backfill_toldot:
        backfill_toldot(load_index())
        return

    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["entries"]
    index = load_index()
    by_title = {v["requested_title"]: k for k, v in index.items()}
    adapter = ADAPTERS[args.source]
    failures = []

    todo = []
    for cand in candidates:
        known = by_title.get(cand["title"])
        if known and not args.force:
            if adapter.load(known)[0] is not None or not args.retry_missing:
                continue
        elif args.retry_missing and not known:
            continue
        todo.append((cand, known))
    print(f"{len(todo)} of {len(candidates)} candidates to fetch", flush=True)

    for start in range(0, len(todo), BATCH):
        batch = todo[start:start + BATCH]
        try:
            pages = adapter.fetch_many([c["title"] for c, _ in batch])
        except Exception as err:  # e.g. the whole API blocked by a filter
            pages = {c["title"]: err for c, _ in batch}

        plan = []  # (cand, eid, meta, wikitext, missing)
        for cand, known in batch:
            result = pages.get(cand["title"])
            if isinstance(result, tuple) and not result[0]["disambiguation"]:
                meta, wikitext = result
                plan.append((cand, meta["wikidata_id"] or known or cand.get("id"), meta, wikitext, None))
            else:
                missing = "disambiguation page" if isinstance(result, tuple) else str(result)
                plan.append((cand, known or cand.get("id"), None, None, missing))

        qids = [eid for _, eid, *_ in plan if eid]
        try:
            wd = wikidata.fetch_many(qids) if qids else {}
        except Exception as err:
            wd, wd_error = {}, str(err)
        else:
            wd_error = None

        for cand, eid, meta, wikitext, missing in plan:
            label = f"[{start + len(failures) + 1}] {cand['title']}"
            if not eid or eid not in wd:
                reason = missing or wd_error or "no Wikidata id"
                failures.append((cand["title"], reason))
                print(f"{label}: FAIL {reason}", flush=True)
                continue
            if wikitext is not None:
                adapter.save(eid, meta, wikitext)
            wikidata.save(eid, wd[eid])
            entry = {"era": cand["era"], "requested_title": cand["title"],
                     "title": meta["title"] if meta else cand["title"]}
            if missing:
                entry["article_missing"] = missing
            index[eid] = entry
            fetch_toldot(eid, entry, meta, wikitext, wd[eid])
            brief.write(eid, entry)
            status = f"WIKIDATA ONLY ({missing})" if missing else f"ok rev {meta['revid']} ({len(wikitext)} chars)"
            print(f"{cand['title']} -> {entry['title']} ({eid}) {status}", flush=True)
        save_index(index)

    if failures:
        print("\nFailures:")
        for title, err in failures:
            print(f"  {title}: {err}")


if __name__ == "__main__":
    main()
