"""Orchestrator helper for a writing run, built on queue.py.

Used by the session that drives the writer agents (see docs/writing-run-filtered.md).
All state stays in data/work/ (claims, attempts, blocked.json), so the helper
can be dropped and rerun at any time.

  python scripts/cycle.py next <batch|-> <worker> [--skip ID ...] [--blocked [--force]] [--blocked-at ID]
      Park the --skip ids (writer judged them out of scope, duplicate, not a real
      person), finish <batch> with a commit, and claim the next batch of SIZE ids
      for <worker> in the documented era order. Prints {"batch": ..., "ids": [...]}.
      --blocked     the writer died on a NetFree block (HTTP 418): park the first
                    unfinished id of the batch as the suspect. Only when the writer
                    saved something; add --force when it died on its very first brief.
      --blocked-at  park this id as the suspect instead (use when the writer's last
                    words show it had already decided about the first unfinished id).
  python scripts/cycle.py finish <batch> [--skip ID ...] [--blocked [--force]] [--blocked-at ID]
      Same as next, without claiming a new batch (use when stopping the run).
  python scripts/cycle.py park ID REASON
  python scripts/cycle.py sweep
      Commit entries that are saved and valid but untracked by git. This happens when
      a claim expired (CLAIM_TTL) during a pause, so finishing it no longer commits.
"""
import csv
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("q", ROOT / "scripts" / "queue.py")
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

ORDER = ["tannaim", "amoraim", "zugot", "savoraim", "geonim", "rishonim", "mikra", "acharonim",
         "acharonei_zmanenu", None]
BLOCKED = ROOT / "data" / "work" / "blocked.json"  # parked ids and why, for the owner and the open-network run
SIZE = 10
ERAS = [e for e in os.environ.get("CYCLE_ERAS", "").split(",") if e]  # restrict claims to these eras

SKIPPED = "skipped by writer (out of scope, duplicate or not a real person)"


def write_json(path, data):
    # Windows sometimes denies the rename while another process holds the file; retry briefly
    for attempt in range(10):
        try:
            return q.write_json(path, data)
        except PermissionError:
            time.sleep(0.5 * (attempt + 1))
    return q.write_json(path, data)


def run(*args):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "queue.py"), *args], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


def park(pid, why):
    attempts = q.load_json(q.ATTEMPTS, {})
    attempts[pid] = q.MAX_ATTEMPTS
    write_json(q.ATTEMPTS, attempts)
    blocked = q.load_json(BLOCKED, {})
    blocked[pid] = why
    write_json(BLOCKED, blocked)


def clean_failures():
    if not q.FAILURES.exists():
        return
    rows = list(csv.reader(open(q.FAILURES, encoding="utf-8-sig")))
    keep = [rows[0]] + [r for r in rows[1:] if r and q.entry_state(r[0]) != "done"]
    with open(q.FAILURES, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(keep)


def finish(batches, skipped, blocked, blocked_at, force):
    # park first: an id left in the pool would be handed out again by the next claim
    for pid in skipped:
        park(pid, SKIPPED)
    if blocked_at:
        park(blocked_at, "NetFree block")
        print("parked suspect:", blocked_at)
        blocked = False
    for batch in [b for b in batches.split(",") if b != "-"]:
        claim = q.load_json(q.CLAIMS / f"{batch}.json", None)
        if claim and blocked:
            pending = [p for p in claim["ids"] if q.entry_state(p) != "done" and p not in skipped]
            if pending and (len(pending) < len(claim["ids"]) or force):
                park(pending[0], f"NetFree block in batch {batch}")
                print("parked suspect:", pending[0])
                blocked = False  # only the first unfinished id overall is the suspect
        print(run("finish", batch, "--commit"))
    clean_failures()


def claim_next(worker):
    got, ids = [], []
    for era in [e for e in ORDER if not ERAS or e in ERAS]:  # fill the batch across eras, in order
        need = SIZE - len(ids)
        if need <= 0:
            break
        out = json.loads(run("claim", "--size", str(need), "--worker", worker, *(["--era", era] if era else [])))
        if out["batch"]:
            got.append(out["batch"])
            ids += out["ids"]
    print(json.dumps({"batch": ",".join(got), "ids": ids}, ensure_ascii=False))


def sweep():
    out = subprocess.run(["git", "status", "--porcelain", "--", "data/entries"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8").stdout
    paths = [l[3:] for l in out.splitlines() if l.startswith("?? ") and l.endswith(".json")]
    done = [p for p in paths if q.entry_state(Path(p).stem) == "done"]
    if not done:
        print("nothing to sweep")
        return
    subprocess.run(["git", "add", "--", *done], cwd=ROOT, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"Add {len(done)} entries left uncommitted by expired claims"],
                   cwd=ROOT, check=True)
    print("committed", len(done), "entries")


def option_ids(flag):
    if flag not in sys.argv:
        return []
    rest = sys.argv[sys.argv.index(flag) + 1:]
    return [a for a in rest[:next((i for i, a in enumerate(rest) if a.startswith("--")), len(rest))]]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd in ("next", "finish"):
        batch, worker = sys.argv[2], (sys.argv[3] if cmd == "next" else None)
        blocked_at = option_ids("--blocked-at")
        finish(batch, option_ids("--skip"), "--blocked" in sys.argv, blocked_at[0] if blocked_at else None,
               "--force" in sys.argv)
        if cmd == "next":
            claim_next(worker)
    elif cmd == "park":
        park(sys.argv[2], " ".join(sys.argv[3:]) or SKIPPED)
    elif cmd == "sweep":
        sweep()
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
