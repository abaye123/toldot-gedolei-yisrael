"""'Seder HaDorot HaMekutzar' by Rabbi Yosef Chaim Shmuel Segron, as published
in the Torat Emet free library (CC BY-NC-SA 2.5, non-commercial, attribution).

The page is one big HTML table: each row has an icon (event type), up to two
years from Creation (birth / death, or start / end), and a short Hebrew note.
Section headings separate the eras. This module parses it into a flat list and
matches rows to a figure by name / alias.

Usage (refresh the raw snapshot):
    python -m sources.seder_hadorot_segron      (run from the scripts/ directory)
"""

import html
import json
import re

from datetime import date
from functools import lru_cache

from .common import http_get, raw_path

NAME = "seder_hadorot_segron"
CREDIT = "seder_hadorot_segron"
LABEL = "סדר הדורות המקוצר - סגרון: הרב יוסף חיים שמואל סגרון (באדיבות מאגר תורת אמת)"
URL = "http://www.toratemetfreeware.com/online/f_01825.html"
AUTHOR_URL = "http://dorot.jimdo.com"
LICENSE = "CC BY-NC-SA 2.5"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc-sa/2.5/"
RAW_FILE = "f_01825.html"

ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
CELL_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.S | re.I)
TITLE_RE = re.compile(r"title='([^']*)'")
HEADING_RE = re.compile(r"<(?:h\d|a name=[^>]*)[^>]*>(.*?)</", re.S | re.I)


def _text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse(page):
    rows, section = [], None
    # Walk the document in order, tracking the most recent heading-like row.
    for m in ROW_RE.finditer(page):
        cells = CELL_RE.findall(m.group(1))
        if not cells:
            continue
        texts = [_text(c) for _, c in cells]
        icon = TITLE_RE.search(m.group(1))
        years = [t for t in texts if re.fullmatch(r"\d{1,4}", t)]
        # The last cell carries the era label ("תקופת התנאים"); blank means unchanged.
        if len(texts) >= 3 and texts[-1] and not re.fullmatch(r"\d{1,4}", texts[-1]):
            section = texts[-1]
            texts = texts[:-1]
        body = max(texts, key=len)
        if not body or re.fullmatch(r"\d{1,4}", body):
            continue
        rows.append({
            "section": section,
            "type": html.unescape(icon.group(1)) if icon else None,
            "years": [int(y) for y in years[:2]],
            "text": body,
        })
    return rows


def refresh():
    """Download the page into the raw snapshot folder."""
    page_bytes = http_get(URL, accept="text/html")
    path, rel = raw_path(NAME, RAW_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(page_bytes)
    meta_path, _ = raw_path(NAME, "meta.json")
    meta_path.write_text(json.dumps({"url": URL, "raw": rel, "encoding": "cp1255",
                                     "retrieved": date.today().isoformat()}, ensure_ascii=False, indent=1), encoding="utf-8")
    load.cache_clear()
    return load()


def raw_rel():
    return raw_path(NAME, RAW_FILE)[1]


@lru_cache(maxsize=1)
def load():
    """Parsed rows of the raw snapshot; each row's `n` is its stable index."""
    path, _ = raw_path(NAME, RAW_FILE)
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run: python -m sources.seder_hadorot_segron")
    rows = parse(path.read_bytes().decode("cp1255", "replace"))
    for n, row in enumerate(rows):
        row["n"] = n
    return tuple(rows)


def _norm(s):
    s = s.replace("״", '"').replace("''", '"').replace("׳", "'")
    return " ".join(s.split())


def match(names, rows=None, limit=4):
    """Rows whose text contains one of the names as a whole phrase.

    Names shorter than 3 letters are ignored (too ambiguous). Longer names
    score higher; the caller (the writer) decides whether a row really
    refers to the figure.
    """
    rows = rows if rows is not None else load()
    keys = sorted({_norm(n) for n in names if n and len(_norm(n).replace('"', "")) >= 3}, key=len, reverse=True)
    scored = []
    for row in rows:
        text = _norm(row["text"])
        for key in keys:
            m = re.search(rf"(?<![א-ת]){re.escape(key)}(?![א-ת])", text)
            if m:
                # Prefer rows that are *about* the figure (name near the start)
                # over rows that merely mention him ("תלמיד הרמב"ם").
                scored.append(((m.start() < 3, len(key), -m.start()), row))
                break
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]


def year_label(y):
    """Year from Creation -> Hebrew-letter year, e.g. 4898 -> ד'תתצ"ח."""
    thousands, rest = divmod(y, 1000)
    letters = ""
    for value, letter in ((400, "ת"), (300, "ש"), (200, "ר"), (100, "ק"), (90, "צ"), (80, "פ"), (70, "ע"),
                          (60, "ס"), (50, "נ"), (40, "מ"), (30, "ל"), (20, "כ"), (10, "י"), (9, "ט"), (8, "ח"),
                          (7, "ז"), (6, "ו"), (5, "ה"), (4, "ד"), (3, "ג"), (2, "ב"), (1, "א")):
        while rest >= value:
            letters += letter
            rest -= value
    letters = letters.replace("יה", "טו").replace("יו", "טז")
    if len(letters) > 1:
        letters = letters[:-1] + '"' + letters[-1]
    elif letters:
        letters += "'"
    prefix = "אבגדהוזחט"[thousands - 1] + "'" if thousands else ""
    return prefix + letters


if __name__ == "__main__":
    print(len(refresh()), "rows")
