"""Save one entry atomically and validate it.

Usage:
    python scripts/save_entry.py <path to a JSON file with the entry>

Writers prepare the entry anywhere (e.g. a scratch file), then call this:
it checks that the JSON parses, writes data/entries/<id>.json through a
temporary file and an atomic rename (so an interrupted write never leaves
a broken entry), and prints the validation result. Exit code 1 on errors.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import validate  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    entry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    target = ROOT / "data" / "entries" / f"{entry['id']}.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(target)
    errors, warnings = validate.validate(target)
    for e in errors:
        print(f"ERROR {e}")
    for w in warnings:
        print(f"warn  {w}")
    print(f"{entry['id']}: {'OK' if not errors else 'INVALID'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
