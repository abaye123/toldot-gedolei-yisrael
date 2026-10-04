# Toldot Gedolei Yisrael - תולדות גדולי ישראל

Short, fixed-format biographical cards of Torah sages and authors, written in
yeshivish Hebrew for students. Every fact in every card records the sources
that support it, so a source can be removed or replaced (for example
Wikipedia by Hamichlol) and the affected content regenerated from the raw
files kept in this repository.

The biographies are published as GitHub releases (one JSON bundle, and a
zip of one file per entry) and shown on the site on GitHub Pages, which
loads the latest release. Locally, `dist/biographies.json` is the bundle and
`site/index.html` is the viewer with the bundle embedded, which opens
directly in a browser.

## Sources

| Source | License | Provides |
|---|---|---|
| Hebrew Wikipedia | CC BY-SA 4.0 | people, narrative, facts |
| Wikidata | CC0 | people, dates, places, relations |
| סדר הדורות המקוצר - סגרון (Torat Emet) | CC BY-NC-SA 2.5 | people, traditional years from Creation |
| תולדות תנאים ואמוראים, Rabbi Aaron Hyman (Wikisource) | public domain book, CC BY-SA 4.0 transcription | people and biographies of Chazal |
| Hamichlol | proprietary - **disabled** | only after written permission |

Each source both proposes people and adds facts: a sage known only from one
Toldot page or one Seder HaDorot row gets a (short) card too. See
`CREDITS.md` for attribution.

## Layout

```
config/            candidate lists, source switches, exclusions, credits
docs/
  style-guide.md   the writing contract: template, register, eras
  data-model.md    claims with provenance, people registry, replacing a source
  writing-run.md   how to write all entries, resumably
  writer-prompt.md the prompt for writer agents
schema/            JSON Schema of one entry
scripts/
  sources/         adapters: wikipedia, wikidata, mediawiki, toldot_tannaim,
                   seder_hadorot_segron(_people), hamichlol (disabled)
  candidates.py    Wikidata candidates
  resolve.py       people registry merged from all sources (data/people.json)
  lookup_missing.py  Wikidata items for sages only other sources know
  scope.py         Orthodox Torah figures only
  fetch.py         raw snapshots (resumable, batched)
  brief.py         raw snapshots -> one brief per person for the writer
  queue.py         resumable work queue for writing entries
  save_entry.py    atomic save + validation of one entry
  validate.py      schema, provenance and style checks
  link_refs.py     link mentioned teachers/students/relatives to their entries
  prune.py         remove a source from all entries
  build_site.py    entries -> dist/biographies.json + site/index.html
data/
  raw/<provider>/  raw snapshots, byte-for-byte as downloaded
  people.json      the people registry
  index.json       people whose snapshots are fetched
  entries/<id>.json  the written cards (master content)
  review/          lists for human decisions (matches, scope, references)
  briefs/          derived, not committed
dist/biographies.json  release bundle: entries + eras + credits
site/index.html        viewer, built from site/template.html
```

## Building

```
pip install mwparserfromhell
python scripts/candidates.py
python scripts/resolve.py
python scripts/scope.py
python scripts/fetch.py --people all
# write entries: docs/writing-run.md
python scripts/link_refs.py
python scripts/validate.py
python scripts/build_site.py
```

## Releases and the site

```
git tag v1.0.0 && git push origin v1.0.0
```

A pushed `v*` tag runs `.github/workflows/release.yml`: it validates the
entries at that tag, builds the assets with `scripts/package_release.py` and
publishes a release with:

- `biographies.json` - the whole bundle (entries, eras, credits, author,
  license, release tag)
- `biographies-files.zip` - `entries/<id>.json`, `meta.json` (everything in
  the bundle but the entries, plus the entry ids in order), the schema,
  `LICENSE`, `NOTICE`, `CREDITS.md`
- `SHA256SUMS`

When the release is done, `.github/workflows/pages.yml` deploys the site:
`site/template.html` as `index.html`, next to `biographies.json` from the
latest release. It also runs when the template changes on `main`, and by
hand. Pages must be set to deploy from GitHub Actions (Settings > Pages >
Source).

Fetching needs an unfiltered network (NetFree blocks the Wikipedia API and
some article pages). Everything after fetching works offline from `data/raw`.

## Replacing a source

```
# disable it in config/sources.json, then:
python scripts/resolve.py && python scripts/scope.py
python scripts/prune.py --drop wikipedia      # keeps facts other sources support
python scripts/fetch.py --people all          # with the new source enabled
python scripts/queue.py status                # entries marked needs_rewrite are rewritten by the writing run
```

## License

The code and the generated biographies are licensed under the GNU Affero
General Public License v3.0 (`LICENSE`). The biographies are original
writing, composed from facts gathered from the sources above, with each
source credited in every entry and in `CREDITS.md`.

**Attribution is required.** As an additional term under section 7(b) of the
AGPL (see `NOTICE`), any use, copy, distribution or adaptation of the
biographies, in whole or in part, must credit **abaye** as their author in a
way visible to its users, e.g. "Biographies edited by abaye" / "הביוגרפיות נערכו ע"י abaye".

The raw source snapshots in `data/raw/` are not covered by this license;
each remains under its original license, listed above and in `CREDITS.md`.
