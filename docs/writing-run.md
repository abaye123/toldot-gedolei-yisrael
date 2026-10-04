# Writing run

How to write all entries, resumably. Run it from a Claude Code session opened
in this repository (it reads `CLAUDE.md`).

## Principles

- **All state is in files.** An entry is done when `data/entries/<id>.json`
  exists, passes `validate.py` and is not `needs_rewrite`. Nothing about
  progress is kept in a session, so a run can stop at any moment (network
  failure, closed session, a break of days) and continue later.
- **Batches are claimed, not assigned.** `scripts/queue.py claim` hands out a
  batch and records a claim with a timestamp. A claim not finished within
  `CLAIM_TTL` (3 hours) expires and its ids return to the pool.
- **Writes are atomic.** Writers save through `scripts/save_entry.py`
  (temporary file + rename), so an interrupted write never leaves a broken
  entry.
- **Failures don't block.** An id that fails `MAX_ATTEMPTS` (3) times is
  parked in `data/review/write-failures.csv`.
- **Every finished batch is a commit** (`queue.py finish <batch> --commit`),
  so git history is also the checkpoint.

## Before starting (or resuming)

```
pip install mwparserfromhell
python scripts/queue.py status         # what is done / missing / claimed / failed, per era
```

Briefs (`data/briefs/`) are not committed; `queue.py claim` rebuilds the
brief of every id it hands out. Raw snapshots are in the repo, so no network
access to the sources is needed for writing.

## The loop

Repeat until `status` shows nothing missing (or only parked failures):

1. Claim batches, one per writer agent, grouped by era for consistency:
   `python scripts/queue.py claim --size 10 --era tannaim --worker w1`
   (prints `{"batch": ..., "ids": [...]}`; `"batch": null` when the era is done).
2. Run one writer agent per batch with the prompt in `docs/writer-prompt.md`
   (`{IDS}` = the batch ids). Several agents may run in parallel - they never
   touch the same files.
3. When an agent finishes: `python scripts/queue.py finish <batch> --commit`.
   Ids that are not done go back to the pool automatically.
4. Every few hundred entries, refresh links and the release:
   ```
   python scripts/link_refs.py
   python scripts/build_site.py
   git add data/entries dist site/index.html data/review && git commit -m "Refresh links and rebuild release"
   ```

If a session dies mid-batch, do nothing special: the claim expires after
3 hours (or release it at once with `queue.py release <batch>`), and the next
`claim` hands those ids out again. Partially written batches keep their
finished entries - `claim` skips ids that are already done.

As a Claude Code workflow: a script that loops claim -> parallel writer
agents -> finish, with the batch ids passed to each agent, is the natural
shape; it needs no state of its own beyond what `queue.py` keeps, so it can be
restarted from scratch at any time.

## Suggested order

Era by era, reviewing a sample after each before moving on:
tannaim, amoraim, zugot, savoraim, geonim, rishonim, mikra, acharonim,
acharonei_zmanenu, then `unknown` (single-source Toldot sages whose era the
writer determines).

## Cost

Roughly 10k tokens for a thin single-source entry and 20k for a rich one;
about 5,000 entries remain (2026-10-04), on the order of 70-100M tokens.
