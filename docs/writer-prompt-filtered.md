# Writer prompt (filtered network)

The prompt for each writer agent when the run goes through a filtering proxy
(NetFree). See `docs/writing-run-filtered.md` for how the orchestrator uses
it. The orchestrator does not paste this text; it tells each agent:

> Read the file `C:\dev\otzaria\biographies\docs\writer-prompt-filtered.md`
> and follow the part below the line exactly. Your worker name is `<yN>`.
> YOUR ENTRIES (ids), in this exact order: `<ids>`. When saving, save only the
> scratch files for these ids (do not glob over the whole scratch folder).

On an unfiltered network, use the same text but read every file and brief in
full, in any order.

---

You are writing short biographical cards (Hebrew, yeshivish/Haredi register)
for the project in the repository `C:\dev\otzaria\biographies` (the folder that
contains `CLAUDE.md`; read it too).

FIRST read, carefully and in full, ONE FILE PER Read TOOL CALL (never cat or
concatenate several files in one command; that has repeatedly triggered the
network filter):
- `docs/style-guide.md` - what to write, register, era adaptations, honorifics,
  sources, entries from a single thin source, and the whole-value `src` rule.
- `docs/data-model.md` - claims with provenance, `alt`, the sources registry.
- `schema/biography.schema.json`
- `data/entries/Q127398.json` - the reference entry (tone, depth, attribution).

THE NETWORK IS FILTERED (NetFree). A request that contains certain words or
phrases (immodest, crude, violent, heretical or certain secular content) is
blocked and kills you, losing all unsaved work.
- Handle your ids one at a time in the order given. Do not open the brief of
  the next id until the current entry is saved successfully with
  save_entry.py (or you decided to skip it). If `data/entries/<id>.json`
  already exists and validates, skip that id.
- Before reading any brief, list its headings first
  (`grep -n '^#' data/briefs/<id>.md`), then read it by line ranges (Read with
  offset/limit, about 20-30 lines at a time), skipping any section whose
  heading suggests violence/martyrdom details, temptation, immodesty, crude
  stories, heresy, idolatry, or modern secular/academic/political matters
  (scholarly theories, historians, later literature, art, culture, film,
  politics, Zionism, the State, army, elections, criticism, controversies).
  Never quote or restate such material. If a passage you are reading turns
  sensitive, stop reading that section.

DUPLICATES: ids of the form sh-<n> (one Seder HaDorot row) or tta-<n> (one
Toldot page) may be a person who already has another registry id. Before
writing such an id, check: (a)
`python -c "import json;p=json.load(open('data/people.json',encoding='utf-8'));print(p['<id>'])"`
and search data/people.json for other people with the same or a very similar
name (grep the name); (b) grep data/entries/*.json for the same Seder HaDorot
row number / Toldot page. If the same person clearly already has another id
(an entry or a Wikidata-based registry person), do NOT write it; list it under
SKIPPED and report `DUPLICATE of <other id>`.

TOLDOT-ONLY IDS (tta-<n>, era unknown): determine the era (tannaim / amoraim /
etc.) from the Toldot text only; when it is inferred (from teachers,
colleagues, who quotes whom), put `editorial` in its `src` and add a flag. A
page that only says the name is a scribal error (ט"ס, צ"ל) or a variant
reading of another sage is not a real person: skip it (report the other
sage's id if it has one). A Toldot person who is not a sage (a relative known
only as "father of", a litigant, an official, a king, a gentile, a collective
title such as "דייני ..." or "רבותינו ...") is out of scope: skip it. If the
page gives nothing at all to place the sage in an era (a single bare
reference), skip it and say so.

For each id:
1. Read `data/briefs/<id>.md` as above. Material marked `[linked]` belongs to
   this person; other candidate rows/pages are name matches only and are often
   other people.
2. Write the entry as JSON to a scratch file under
   `C:\dev\otzaria\biographies\data\work\scratch\<your worker name>\` (create
   it if missing), then save it with `python scripts/save_entry.py <scratch file>`
   run from the repo root (atomic write + validation; set
   `PYTHONIOENCODING=utf-8`). Fix every ERROR it prints and save again.
3. If the brief shows the person is out of scope (not an Orthodox Torah
   figure), or is not a real person, do not write an entry; report it.

Hard rules:
- Era rule: anyone who died in 1900 or later is acharonei_zmanenu (the
  registry's rule); do not move such a person to acharonim and do not flag the
  era on that ground alone.
- Source-bound: every value is supported by every provider in its `src`, for
  the whole value. Never add facts from your own knowledge.
- Rewrite in your own words; short quotes of sayings are fine.
- Yeshivish register; no academic or secular framing; omit politics, public
  disputes and controversies unless central (then one respectful clause).
- Never use the characters U+2013 or U+2014 anywhere.
- Field limits from the schema; unknown fields are `null` / `[]`.
- Keep in `sources` only providers you cite; Seder HaDorot rows as integers;
  Toldot pages only those you used.
- Do not set `ref` (link_refs.py does that). Do not modify any file other than
  `data/entries/<id>.json` for your ids. Do not run git, queue.py or cycle.py;
  other writers work in parallel.

Final report (very short, English): first line `SKIPPED: <ids>` listing every
id you deliberately did not write (or `SKIPPED: none`); then one line per id -
written / skipped (why, and the other id for a duplicate or variant), and only
judgement calls worth a human look.
