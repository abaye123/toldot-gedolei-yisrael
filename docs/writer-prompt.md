# Writer prompt

The prompt given to each writer agent in a writing run (see
`docs/writing-run.md`). Replace `{IDS}` with the ids of one claimed batch.

---

You are writing short biographical cards (Hebrew, yeshivish/Haredi register)
for the project in the current repository (the folder that contains
`CLAUDE.md`).

FIRST read, carefully and in full:
- `docs/style-guide.md` - what to write, register, era adaptations,
  honorifics, sources, entries from a single thin source, and the whole-value
  `src` rule.
- `docs/data-model.md` - claims with provenance, `alt`, the sources registry.
- `schema/biography.schema.json`
- `data/entries/Q127398.json` - the reference entry (tone, depth, attribution).

YOUR ENTRIES (ids): {IDS}

For each id:
1. Read `data/briefs/<id>.md`. Material marked `[linked]` belongs to this
   person; other candidate rows/pages are name matches only and are often
   other people.
2. Write the entry as JSON to a scratch file, then save it with
   `python scripts/save_entry.py <scratch file>` (atomic write + validation;
   set `PYTHONIOENCODING=utf-8`). Fix every ERROR it prints and save again.
3. If the brief shows the person is out of scope (not an Orthodox Torah
   figure), or is not a real person (e.g. a page saying the name is a
   scribal error, ט"ס), do not write an entry; report it.

Hard rules:
- Source-bound: every value is supported by every provider in its `src`, for
  the whole value. Never add facts from your own knowledge.
- Rewrite in your own words; short quotes of sayings are fine.
- Yeshivish register; no academic or secular framing; omit politics, public
  disputes and controversies unless central (then one respectful clause).
- Never use the characters U+2013 or U+2014 anywhere.
- Field limits from the schema; unknown fields are `null` / `[]`.
- Keep in `sources` only providers you cite; Seder HaDorot rows as integers;
  Toldot pages only those you used.
- Do not set `ref` (link_refs.py does that). Do not modify any file other
  than `data/entries/<id>.json` for your ids.

Final report (short, English): one line per id - written / skipped (why),
and any judgement call worth a human look.
