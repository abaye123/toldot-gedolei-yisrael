"""Name normalisation shared by matching code (resolve.py, source adapters).

Two names refer to the same sage when their keys intersect. A key is the
name without titles and honorifics, with spelling variants folded:
    "רבי משה בן מימון זצ"ל" -> "משה ב מימון"
    "הרמב״ם"               -> "רמבם"
"""

import re

TITLES = ("רבינו", "רבנו", "רבן", "רבי", "ר'", "רב", "הרב", "הגאון", "מרן", "מורנו", "הגה\"ק", "הצדיק", "האדמו\"ר", "אדמו\"ר")
HONORIFICS = ("זצ\"ל", "זצוק\"ל", "זי\"ע", "ז\"ל", "ע\"ה", "הי\"ד", "זיע\"א", "שליט\"א", "נ\"ע")


def fold(s):
    """Unify quote characters and spacing."""
    s = s.replace("״", '"').replace("''", '"').replace("׳", "'").replace("`", "'")
    s = s.replace("‫", "").replace("‬", "").replace("‏", "")
    return " ".join(s.split())


def key(name):
    """Comparison key of one name, or '' if nothing distinctive is left."""
    s = fold(name)
    s = re.sub(r"\([^)]*\)", " ", s)
    for h in HONORIFICS:
        s = s.replace(h, " ")
    words = s.split()
    while words and words[0] in TITLES:
        words = words[1:]
    s = " ".join(words)
    # Acronyms: drop the quote mark and a leading definite article (הרמב"ם -> רמבם).
    if '"' in s and " " not in s:
        s = s.replace('"', "")
        if s.startswith("ה") and len(s) >= 3:
            s = s[1:]
    s = s.replace('"', "").replace("'", "")
    s = re.sub(r"\s(בן|בר|ב)\s", " ב ", f" {s} ").strip()
    return s if len(s.replace(" ", "")) >= 2 else ""


def keys(names):
    out = set()
    for n in names:
        k = key(n) if n else ""
        if k:
            out.add(k)
            # "בעל חוות יאיר" ~ "חוות יאיר": a sage called by his book.
            if k.startswith("בעל "):
                out.add(k[4:])
            # "החפץ חיים" ~ "חפץ חיים": book-names appear with and without the article.
            if k.startswith("ה") and " " in k:
                out.add(k[1:])
    return out


# Common abbreviations, expanded before comparing loosely.
ABBREVIATIONS = {'יו"ט': "יום טוב", 'מהר"ר': "", 'הר"ר': "", 'כמוהר"ר': "", 'מוהר"ר': ""}


def loose_key(name):
    """A forgiving key: abbreviations expanded, matres lectionis (ו, י) and
    geresh dropped, so "סולוביצ'ק" ~ "סולובייצ'יק". Only for use together
    with other evidence (era, years)."""
    s = fold(name)
    for abbr, full in ABBREVIATIONS.items():
        s = s.replace(abbr, full)
    k = key(s)
    return "".join(ch for ch in k if ch not in "וי'") if k else ""


def loose_keys(names):
    out = set()
    for n in names:
        k = loose_key(n) if n else ""
        if len(k.replace(" ", "")) >= 4:
            out.add(k)
            words = k.split()
            # "...סלבצק מברסק" ~ "...סלבצק": a trailing place ("מבריסק") is optional.
            # "הל" is the loose form of "הלוי".
            if len(words) >= 3 and (words[-1].startswith("מ") or words[-1] in ("הל", "הכהן", "סגל")):
                out.add(" ".join(words[:-1]))
    return out


def creation_to_ce(year):
    """Year from Creation -> approximate year CE (negative = BCE)."""
    return year - 3760
