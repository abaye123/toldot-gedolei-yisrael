# Data Model

Goal: every piece of information in every entry knows which source it came
from, so a source can be removed or replaced (e.g. Wikipedia -> Hamichlol) and
the affected content regenerated from the raw files, as if writing for the
first time.

## Who is in the collection: the people registry

Every source can contribute people, not only facts. `scripts/resolve.py`
collects proposals from all enabled sources (Wikidata candidates, Toldot
Tannaim veAmoraim biography pages, Seder HaDorot person rows), merges those
that are the same person (names + era + years), and writes
`data/people.json`:

```json
"tta-9981": {
  "id": "tta-9981", "origin": "toldot_tannaim", "era": "amoraim", "name": "ר' אבא בר זבדא",
  "names": ["..."], "born_ce": null, "died_ce": null,
  "links": {"toldot_tannaim": ["תולדות תנאים ואמוראים/א/ר' אבא בר זבדא"], "seder_hadorot_segron": [301]},
  "source_keys": ["toldot_tannaim:9981", "seder_hadorot_segron:301"]
}
```

- Ids are assigned once, from the source that first proposed the person
  (`Q...`, `tta-<pageid>`, `sh-<row>`), and never change, so an id says
  nothing about which sources an entry uses today.
- Uncertain merges are not guessed: they go to
  `data/review/resolve-ambiguous.csv`; decisions are recorded in
  `data/review/overrides.json` (`{"<source key>": "<person id>" | "new" | "skip"}`)
  and survive every re-run.
- `fetch.py --people <ids file | era=..,origin=..,limit=N>` fetches what the
  selected people link to; their briefs mark registry-linked material `[linked]`.
- Removing a source: disable it in `config/sources.json`, re-run
  `resolve.py`, and `prune.py --drop <source>`; entries that came from that
  source alone are deleted.

## Layers

```
data/raw/<provider>/...          1. raw snapshots, exactly as fetched (committed)
data/briefs/<id>.md              2. writer's brief, derived from raw (regenerable, not committed)
data/entries/<id>.json           3. master content: claims with provenance (committed)
dist/biographies.json            4. release bundle = entries + credits registry (built)
site/index.html                  5. viewer (built)
```

Layers 2, 4 and 5 are always rebuilt from 1 and 3, never edited by hand.

### Raw snapshots (`data/raw/<provider>/`)

| Provider | Files | Notes |
|---|---|---|
| `wikipedia` | `<id>.wikitext`, `<id>.meta.json` | page source as stored by MediaWiki; meta has title, page id, revision id, timestamp, url, retrieved |
| `wikidata` | `<id>.json` | `wbgetentities` response (he/en labels, aliases, claims, hewiki sitelink) plus labels of linked items |
| `seder_hadorot_segron` | `f_01825.html`, `meta.json` | the whole page, once; rows are addressed by index |
| `toldot_tannaim` | `index.json`, `<pageid>.html`, `<pageid>.meta.json` | Wikisource pages of Toldot Tannaim veAmoraim (Chazal only); entries cite `{"pages": [{title, url, revid, raw}], "credit"}` |
| `hamichlol` | `<id>.wikitext`, `<id>.meta.json` | same as wikipedia; only after permission |

The revision id pins the exact text that was used, so any entry can be
traced back to (and re-derived from) a specific version of the article.

## Entry (`data/entries/<id>.json`)

```json
{
  "id": "Q127398",
  "sources": {
    "wikipedia": {
      "title": "רמב\"ם", "url": "https://he.wikipedia.org/wiki/...", "revid": 44001005,
      "retrieved": "2026-10-04", "raw": "data/raw/wikipedia/Q127398.wikitext", "credit": "wikipedia"
    },
    "wikidata": {
      "id": "Q127398", "url": "https://www.wikidata.org/wiki/Q127398",
      "retrieved": "2026-10-04", "raw": "data/raw/wikidata/Q127398.json", "credit": "wikidata"
    },
    "seder_hadorot_segron": {
      "rows": [598], "url": "http://www.toratemetfreeware.com/online/f_01825.html",
      "raw": "data/raw/seder_hadorot_segron/f_01825.html", "credit": "seder_hadorot_segron"
    }
  },
  "era": {"value": "rishonim", "src": ["wikipedia", "wikidata"]},
  "fields": {
    "name":        {"value": "רבינו משה בן מימון", "src": ["wikipedia"]},
    "known_as":    [{"value": "הרמב\"ם", "src": ["wikipedia", "wikidata"]}],
    "honorific":   {"value": "זצ\"ל", "src": ["editorial"]},
    "generation":  null,
    "region":      [{"value": "ספרד", "src": ["wikipedia"]}, {"value": "מצרים", "src": ["wikipedia"]}],
    "born": {
      "hebrew":    {"value": "ד'תתצ\"ח", "src": ["wikipedia"],
                    "alt": [{"value": "ד'תתצ\"ה", "src": ["seder_hadorot_segron"]}]},
      "gregorian": {"value": "1138", "src": ["wikipedia", "wikidata"]},
      "place":     {"value": "קורדובה", "src": ["wikipedia", "wikidata"]}
    },
    "died":        {"hebrew": {...}, "gregorian": {...}, "place": {...}},
    "buried":      {"value": "טבריה", "src": ["wikipedia", "wikidata"]},
    "roles":       [],
    "teachers":    [{"value": "רבי יוסף אבן מיגאש", "src": ["wikipedia"]}],
    "students":    [],
    "family":      [{"value": {"relation": "אביו", "name": "רבי מימון הדיין"}, "src": ["wikipedia", "wikidata"]}],
    "works":       [{"value": {"title": "משנה תורה", "description": "חיבור הלכתי הכולל את כל דיני התורה"}, "src": ["wikipedia"]}],
    "mentioned_in": null,
    "summary":     {"value": "...", "src": ["wikipedia"]},
    "remember":    {"value": "...", "src": ["wikipedia"]}
  },
  "review": {"status": "draft", "flags": [], "written": "2026-10-04"}
}
```

### Claims

Every leaf of `fields` is a **claim** (or `null` / `[]` when unknown):

```json
{"value": <string | object>, "src": ["<provider>", ...], "alt": [<claim>, ...]}
```

- `src` lists every provider that supports the value. A fact found in two
  sources lists both - that is what lets it survive removal of one of them.
- `alt` (optional) holds competing values from other sources (e.g. two
  traditions for a birth year). The main `value` is the preferred one.
- `ref` (optional, on teachers / students / family claims) is the id in
  `data/people.json` of the person mentioned, so the card can link to his
  own entry. It is set by `scripts/link_refs.py` (from Wikidata relations
  first, then unique name + era matches), never by hand in the entry;
  manual decisions go to `data/review/ref-overrides.json`.
- `editorial` is a pseudo-provider for conventions applied by the writer and
  not taken from any source (honorifics, the customary form of a title). It
  needs no credit.
- Composed prose (`summary`, `remember`, work `description`) lists every
  source it drew on.

### Source registry

`sources` maps each provider key used in the entry's claims to where the
material came from: a link to the original page (`url`), a link to the raw
snapshot in this repository (`raw`), version info (`revid`, `retrieved`,
`rows`), and a `credit` key into `config/credits.json`. The full license and
attribution text lives once in `config/credits.json` / `CREDITS.md`.

## Replacing or removing a source

```
python scripts/prune.py --drop wikipedia
```

For every entry:
1. Removes `wikipedia` from every `src`.
2. Drops atomic claims whose `src` became empty; claims still supported by
   another source stay (with the remaining providers).
3. Drops composed prose that used the dropped source (it can't be split),
   and promotes an `alt` value when the main value was dropped.
4. Removes the provider from `sources` and sets `review.status` to
   `needs_rewrite` with a flag naming the dropped source.

Then fetch the new source (`fetch.py --source hamichlol`), rebuild the briefs,
and run the writers on `needs_rewrite` entries. They fill the gaps from the
new material and keep every remaining claim. To start over completely, delete
`data/entries/` and rewrite from the raw snapshots.

## Release bundle (`dist/biographies.json`)

```json
{
  "format": "biographies", "version": 2, "built": "2026-10-04",
  "eras": [{"key": "mikra", "label": "תקופת המקרא"}, ...],
  "credits": { "<credit key>": { ...from config/credits.json } },
  "entries": [ <entry>, ... ]
}
```

Entries are included as-is (claims and provenance kept). Consumers that only
need the text read `fields.*.value`.
