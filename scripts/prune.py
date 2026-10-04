"""Remove a source from all entries, keeping what other sources support.

Usage:
    python scripts/prune.py --drop wikipedia [--dry-run]

Entries that came from the dropped source alone are deleted. Also disable the
source in config/sources.json so resolve.py stops proposing its people.

See docs/data-model.md, "Replacing or removing a source". Afterwards fetch
the replacement source, rebuild the briefs, and rewrite the entries whose
review.status is `needs_rewrite`.
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRIES = ROOT / "data" / "entries"

# Composed prose cannot be split by source: drop it whenever a source it used is dropped.
PROSE_PATHS = {"summary", "remember"}


def prune_claim(claim, provider, prose):
    """Return the claim without `provider`, or None if nothing supports it any more."""
    if claim is None:
        return None
    alts = [a for a in (prune_claim(a, provider, prose) for a in claim.get("alt", [])) if a]
    if provider in claim["src"] and (prose or claim["src"] == [provider]):
        if alts:  # promote the first surviving alternative
            head, rest = alts[0], alts[1:]
            return {**head, **({"alt": rest} if rest else {})}
        return None
    out = {**claim, "src": [s for s in claim["src"] if s != provider]}
    if alts:
        out["alt"] = alts
    else:
        out.pop("alt", None)
    return out


def prune_entry(entry, provider):
    fields = entry["fields"]
    changed = provider in entry["sources"]
    for key, value in fields.items():
        if isinstance(value, list):
            # Work descriptions are prose too, but the title alone may survive.
            kept = []
            for c in value:
                if key == "works" and provider in c["src"] and c["src"] != [provider]:
                    c = {**c, "value": {**c["value"], "description": None}}
                pc = prune_claim(c, provider, prose=False)
                if pc:
                    kept.append(pc)
            fields[key] = kept
        elif isinstance(value, dict) and "src" not in value:  # born / died
            fields[key] = {k: prune_claim(v, provider, prose=False) for k, v in value.items()}
        else:
            fields[key] = prune_claim(value, provider, prose=key in PROSE_PATHS)
    era = prune_claim(entry["era"], provider, prose=False)
    entry["era"] = era or {**entry["era"], "src": ["editorial"]}
    entry["sources"].pop(provider, None)
    if changed:
        entry["review"]["status"] = "needs_rewrite"
        entry["review"]["flags"].append(f"source '{provider}' removed; refill missing fields from the new sources")
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drop", required=True, help="provider key, e.g. wikipedia")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    count = deleted = 0
    for path in sorted(ENTRIES.glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        if prune_entry(entry, args.drop):
            count += 1
            if not entry["sources"]:  # nothing left: the person came from this source only
                deleted += 1
                if not args.dry_run:
                    path.unlink()
            elif not args.dry_run:
                path.write_text(json.dumps(entry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    verb = "would be " if args.dry_run else ""
    print(f"{count} entries {verb}pruned of '{args.drop}', {deleted} of them {verb}deleted (no source left)")


if __name__ == "__main__":
    main()
