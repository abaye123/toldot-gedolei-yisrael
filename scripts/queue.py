"""Resumable work queue for writing entries.

All state lives in files, so a writing run survives network failures,
crashed sessions and breaks of hours or days:
  - done      = data/entries/<id>.json exists, passes validate.py and is not
                marked needs_rewrite (recomputed every time, never stored)
  - claims    = data/work/claims/<batch>.json; a claim older than CLAIM_TTL is
                stale and its ids return to the pool automatically
  - attempts  = data/work/attempts.json; an id that failed MAX_ATTEMPTS times
                is parked in data/review/write-failures.csv instead of
                blocking the run
See docs/writing-run.md for the procedure.

Usage:
    python scripts/queue.py status
    python scripts/queue.py claim --size 10 [--era tannaim] [--worker w1]   -> prints {"batch", "ids"}
    python scripts/queue.py finish <batch> [--commit]
    python scripts/queue.py release <batch>
"""

import argparse
import csv
import json
import subprocess
import sys
import time
import uuid
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import brief  # noqa: E402
import validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "data" / "work"
CLAIMS = WORK / "claims"
ATTEMPTS = WORK / "attempts.json"
FAILURES = ROOT / "data" / "review" / "write-failures.csv"
ENTRIES = ROOT / "data" / "entries"

CLAIM_TTL = 3 * 3600  # seconds; a batch not finished by then is given out again
MAX_ATTEMPTS = 3
ERA_ORDER = ["mikra", "zugot", "tannaim", "amoraim", "savoraim", "geonim", "rishonim", "acharonim",
             "acharonei_zmanenu", None]


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write_json(path, data):
    """Write atomically: a crash never leaves a half-written state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def entry_state(pid):
    path = ENTRIES / f"{pid}.json"
    if not path.exists():
        return "missing"
    errors, _ = validate.validate(path)
    if errors:
        return "invalid"
    if json.loads(path.read_text(encoding="utf-8")).get("review", {}).get("status") == "needs_rewrite":
        return "needs_rewrite"
    return "done"


def active_claims():
    now, out = time.time(), {}
    for path in CLAIMS.glob("*.json") if CLAIMS.exists() else []:
        claim = load_json(path, {})
        if now - claim.get("claimed_at", 0) > CLAIM_TTL:
            path.unlink(missing_ok=True)  # stale: the worker is gone
            continue
        out[path.stem] = claim
    return out


def in_scope():
    people = load_json(ROOT / "data" / "people.json", {})
    index = load_json(ROOT / "data" / "index.json", {})
    return {pid: p for pid, p in people.items() if p.get("scope") == "ok" and pid in index}


def era_key(p):
    return ERA_ORDER.index(p.get("era")) if p.get("era") in ERA_ORDER else len(ERA_ORDER)


def cmd_status(_args):
    people, attempts = in_scope(), load_json(ATTEMPTS, {})
    claimed = {i for c in active_claims().values() for i in c["ids"]}
    counts = Counter()
    for pid, p in people.items():
        state = entry_state(pid)
        if state != "done":
            if pid in claimed:
                state = "claimed"
            elif attempts.get(pid, 0) >= MAX_ATTEMPTS:
                state = "failed"
        counts[(p.get("era") or "unknown", state)] += 1
    eras = sorted({e for e, _ in counts}, key=lambda e: ERA_ORDER.index(e) if e in ERA_ORDER else 99)
    states = ["done", "missing", "invalid", "needs_rewrite", "claimed", "failed"]
    print(f"{'era':20}" + "".join(f"{s:>14}" for s in states))
    for era in eras:
        print(f"{era:20}" + "".join(f"{counts[(era, s)]:>14}" for s in states))
    print(f"{'total':20}" + "".join(f"{sum(v for (e, st), v in counts.items() if st == s):>14}" for s in states))


def cmd_claim(args):
    people, attempts = in_scope(), load_json(ATTEMPTS, {})
    claimed = {i for c in active_claims().values() for i in c["ids"]}
    pool = [p for pid, p in people.items()
            if pid not in claimed and attempts.get(pid, 0) < MAX_ATTEMPTS
            and (not args.era or p.get("era") == args.era)]
    pool.sort(key=lambda p: (era_key(p), p["id"]))
    ids = []
    for p in pool:  # checking state is the slow part, so stop as soon as the batch is full
        if entry_state(p["id"]) != "done":
            ids.append(p["id"])
            if len(ids) >= args.size:
                break
    if not ids:
        print(json.dumps({"batch": None, "ids": []}))
        return
    for pid in ids:
        brief.write(pid)  # briefs are derived files; make sure they exist and are current
        attempts[pid] = attempts.get(pid, 0) + 1
    batch = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    write_json(CLAIMS / f"{batch}.json", {"ids": ids, "worker": args.worker, "claimed_at": time.time()})
    write_json(ATTEMPTS, attempts)
    print(json.dumps({"batch": batch, "ids": ids}, ensure_ascii=False))


def cmd_finish(args):
    path = CLAIMS / f"{args.batch}.json"
    claim = load_json(path, None)
    if claim is None:
        print(f"no active claim {args.batch} (expired or finished); checking nothing")
        return
    attempts = load_json(ATTEMPTS, {})
    done, failed = [], []
    for pid in claim["ids"]:
        (done if entry_state(pid) == "done" else failed).append(pid)
    for pid in done:
        attempts.pop(pid, None)
    parked = [pid for pid in failed if attempts.get(pid, 0) >= MAX_ATTEMPTS]
    if parked:
        FAILURES.parent.mkdir(parents=True, exist_ok=True)
        new_file = not FAILURES.exists()
        with open(FAILURES, "a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["id", "state", "batch"])
            w.writerows([pid, entry_state(pid), args.batch] for pid in parked)
    write_json(ATTEMPTS, attempts)
    path.unlink(missing_ok=True)
    print(json.dumps({"batch": args.batch, "done": done, "retry": [p for p in failed if p not in parked],
                      "parked": parked}, ensure_ascii=False))
    if args.commit and done:
        files = [str(ENTRIES / f"{pid}.json") for pid in done]
        subprocess.run(["git", "add", *files], cwd=ROOT, check=True)
        people = load_json(ROOT / "data" / "people.json", {})
        names = ", ".join(people.get(pid, {}).get("name", pid) for pid in done[:6])
        more = f" and {len(done) - 6} more" if len(done) > 6 else ""
        msg = f"Add {len(done)} entries: {names}{more}"
        subprocess.run(["git", "commit", "-q", "-m", msg, "--", *files], cwd=ROOT, check=True)


def cmd_release(args):
    (CLAIMS / f"{args.batch}.json").unlink(missing_ok=True)
    print(f"released {args.batch}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    c = sub.add_parser("claim")
    c.add_argument("--size", type=int, default=10)
    c.add_argument("--era")
    c.add_argument("--worker", default="")
    f = sub.add_parser("finish")
    f.add_argument("batch")
    f.add_argument("--commit", action="store_true", help="commit the finished entries")
    r = sub.add_parser("release")
    r.add_argument("batch")
    args = ap.parse_args()
    {"status": cmd_status, "claim": cmd_claim, "finish": cmd_finish, "release": cmd_release}[args.cmd](args)


if __name__ == "__main__":
    main()
