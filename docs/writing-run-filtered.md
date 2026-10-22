# Writing run on a filtered network - orchestrator guide

How a Claude Code session drives the writer agents, as learned in the runs of
2026-10-05/06 (about 3,700 entries, behind NetFree). Give this file to any new
session that continues the run. It extends `docs/writing-run.md`; read that,
`CLAUDE.md` and `README.md` first.

## The setup in one paragraph

The orchestrating session never writes entries itself. It claims batches of
10 ids with `scripts/cycle.py`, runs one background writer agent per batch
(7 in parallel, workers `y1`..`y7`), and when an agent reports back it finishes
the batch (one commit per batch) and gives that worker the next batch. All
state is in files (`data/work/`, git), so a new session can take over at any
point with nothing but this repo.

## Starting or resuming

1. `PYTHONIOENCODING=utf-8 python scripts/queue.py status` - done / missing /
   claimed / failed per era.
2. `ls data/work/claims` - open claims. A claim from a session that is gone:
   release it (`python scripts/queue.py release <batch>`); its saved entries
   stay, its unsaved ids return to the pool.
3. `python scripts/cycle.py sweep` - commit entries that are saved but
   untracked (claims expire after 3 hours, so after a long pause their entries
   are left out of the batch commit).
4. Claim 7 batches, one per worker: `python scripts/cycle.py next - y1`
   (prints `{"batch": ..., "ids": [...]}`), and so on for y2..y7.
5. Launch one writer per batch with the Agent tool, `subagent_type:
   general-purpose`, `run_in_background: true`, and this prompt:

   > Read the file C:\dev\otzaria\biographies\docs\writer-prompt-filtered.md and
   > follow the part below the line exactly. Your worker name is y1. YOUR ENTRIES
   > (ids), in this exact order: <ids>. When saving, save only the scratch files
   > for these ids (do not glob over the whole scratch folder).

   Add "Be extra careful about the network filter: read briefs in small ranges
   and skip sensitive passages entirely." when the batch continues one that was
   blocked.

## The loop

When a writer reports (its report starts with `SKIPPED: ...`):

```
python scripts/cycle.py next <batch> <worker> --skip <every id in its SKIPPED line>
```

This parks the skipped ids (so no later claim hands them out again), commits
the batch, and claims the worker's next batch; launch the next writer with it.
Append the judgement calls from the report to `data/review/writing-run-notes.md`
(one line per batch: what was skipped and why, possible duplicates and merges,
scope doubts, honorific doubts). Do this for every report as it arrives; do
not wait for the others.

To stop the run: `python scripts/cycle.py finish <batch> --skip ...` for each
report, without claiming. Stop the writers only by not giving them new batches;
a running batch is left to finish.

## NetFree blocks (HTTP 418)

An agent that dies with `API Error: 418 I'm a Teapot` (sometimes
`blockByNetFree`) was blocked by NetFree because of words in its request. It is
not an outage; do not stop or ask. The agent's last message (in the
notification) tells where it was.

- It saved some entries: `python scripts/cycle.py next <batch> <worker> --blocked`
  parks the first unsaved id as the suspect and gives the rest out again.
- It died on its first brief ("Now the first id"): add `--force`.
- Its last words show it had already decided to skip the first unsaved id
  (for example "Skip tta-X. Next: tta-Y"): use `--skip tta-X --blocked-at tta-Y`
  so the decided skip is not mistaken for the suspect.
- Several agents blocked at once is normal; handle each the same way.
- Relaunch with the "extra careful" sentence. Parked suspects wait in
  `data/work/blocked.json` for a run on an open network (see below).

A plain `server_error` or a malformed stream is not a block: just give the same
ids out again.

## Pitfalls met so far

- Park skips before claiming. A skipped id that is not parked goes back to the
  pool and is handed to the next writer, who reads it again.
- A claim older than 3 hours expires and its ids return to the pool. After a
  usage-limit pause, finish the old batches first (with their skips), then run
  `sweep`, then claim; if a new claim already picked up skipped ids, park them
  and `queue.py release` that claim.
- On Windows, renaming `attempts.json` sometimes fails with "Access is
  denied"; `cycle.py` retries. If a raw `queue.py` call fails that way, delete
  the leftover `.tmp` file and rerun.
- Never pass a batch id with a typo to `cycle.py next`: the finish fails
  silently and a second batch is claimed for the same worker.
- The usage limit: before it runs out, schedule the resume with CronCreate (a
  one-shot a few minutes after the reset) whose prompt repeats this guide's
  "Starting or resuming" steps. It lives only in the session; the computer must
  stay on.
- Scratch files of the writers go to `data/work/scratch/` (ignored by git), not
  to the system temp folder, which is cleaned and lost the helper scripts and
  notes once.
- Commit messages: the change only, no AI credit lines (see `CLAUDE.md`).

## What the writers learned (already in the prompt)

- Single Seder HaDorot rows (`sh-<n>`) are mostly people who already have a
  Wikidata entry: in one batch 9 of 10 were duplicates.
- About half of the Toldot pages (`tta-<n>`) are not a separate sage: scribal
  errors (צ"ל, ט"ס), variant readings of another sage, collective titles,
  relatives known only as "father of", litigants, kings. The writers skip them
  and name the other id. Batches of Toldot ids therefore yield about 5-7
  entries each.
- Toldot eras are mostly inferred (`src: ["editorial"]` with a flag).
- Writers that read briefs in full on a filtered network get blocked; reading
  headings first and then ranges of 20-30 lines keeps blocks to a few percent.

## Reporting to the owner

The owner reads Hebrew. Report in Hebrew, short: after each few batches what
was written, what was skipped, and only the items that need the owner's
decision. Status on request:
`queue.py status`, `git log --oneline | head`, size of `data/work/blocked.json`.

## Open decisions (waiting for the owner)

Collected in `data/review/writing-run-notes.md`. The main ones:

1. Scope exclusions for people that `scope.py` marked in scope but the writers
   found out of scope (academics, a comedian, politicians) - add to
   `data/review/scope-overrides.json`.
2. Duplicates to merge in `data/review/overrides.json` (single Seder HaDorot
   rows and Toldot pages of people who already have an entry).
3. Wrong registry links (for example a modern rabbi linked to a Toldot page of
   an amora; wrong Seder HaDorot rows).
4. One rule for honorifics: זצ"ל / זי"ע / הי"ד, and ע"ה for women.
5. Borderline entries that were written and may be removed.
6. Single-mention Toldot sages with no era in the text: write them with an
   editorial era guess, or skip them. Writers did both so far.
7. Detect scribal-error and cross-reference Toldot pages automatically (see
   "Known issues" in `CLAUDE.md`), which would save about half of the Toldot
   writing time.

## The open-network run

When the owner says the network is open: run the parked NetFree suspects
(`data/work/blocked.json`, reasons starting with "NetFree block") with
`docs/writer-prompt.md` (reading in full). Unpark an id by lowering its count in
`data/work/attempts.json` below `MAX_ATTEMPTS` and removing it from
`blocked.json`; ids parked as skipped stay parked until the owner decides.
