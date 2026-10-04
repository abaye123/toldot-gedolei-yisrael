"""'Toldot Tannaim veAmoraim' by Rabbi Aaron Hyman (1910), via Hebrew Wikisource.

The book is in the public domain (the author died in 1937); the Wikisource
transcription is CC BY-SA 4.0. Wikisource has one page per sage under
`תולדות תנאים ואמוראים/<letter>/<name>`; the transcription is partial
(some letters are missing entirely).

Most sage pages hold no text of their own: they transclude a section of the
scanned book (`<pages index="..." onlysection="..." from=X to=Y />`), whose
text lives on pages in the "עמוד:" (Page:) namespace. refresh_index() reads the
wikitext of every sage page and of every scan page it points to (batched,
up to 50 titles per request); index_entries() cuts out each page's section
and classifies the page (bio / list / xref / redirect / empty) without
downloading rendered HTML.

Used for Zugot, Tannaim, Amoraim and Savoraim only. Raw snapshots:
    data/raw/toldot_tannaim/index.json          all sage pages + metadata (see refresh_index)
    data/raw/toldot_tannaim/scans.json          wikitext of the transcluded scan pages
    data/raw/toldot_tannaim/<pageid>.html       rendered page (action=parse)
    data/raw/toldot_tannaim/<pageid>.meta.json  title, revid, url, retrieved

Usage (refresh the page index):
    python -m sources.toldot_tannaim      (run from the scripts/ directory)
"""

import difflib
import json
import re
import urllib.parse
from datetime import date
from html.parser import HTMLParser

import mwparserfromhell

from .common import http_json, quote_title, raw_path

NAME = "toldot_tannaim"
CREDIT = "toldot_tannaim"
SITE = "https://he.wikisource.org"
API = f"{SITE}/w/api.php"
PREFIX = "תולדות תנאים ואמוראים/"
ERAS = {"zugot", "tannaim", "amoraim", "savoraim"}

# Pages longer than this are cut in the brief (the longest run to ~100k chars).
MAX_PAGE_CHARS = 80000

# MediaWiki allows 50 titles per query (and 50 revisions with content).
BATCH = 50
# Requests are GETs; keep the encoded `titles` parameter well below the
# ~8 KB URI limit (HTTP 414 otherwise).
MAX_URL_PARAM = 6000

# Bumped when the index.json layout changes; an older file is rebuilt.
INDEX_VERSION = 3

BIDI = {ord(c): None for c in "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\ufeff"}


# ---------------------------------------------------------------------------
# Index: fetching

def _api(**params):
    return http_json(f"{API}?" + urllib.parse.urlencode(
        {"format": "json", "formatversion": 2, **params}))


def _batches(items, size=BATCH, max_url=MAX_URL_PARAM):
    """Chunks of up to `size` titles whose joined, URL-encoded form stays under
    `max_url` characters (50 Hebrew titles would exceed the server's URI limit)."""
    batch, used = [], 0
    for item in items:
        cost = len(urllib.parse.quote(item)) + 3
        if batch and (len(batch) >= size or used + cost > max_url):
            yield batch
            batch, used = [], 0
        batch.append(item)
        used += cost
    if batch:
        yield batch


def _list_titles():
    titles, cont = [], {}
    while True:
        data = _api(action="query", list="allpages", apprefix=PREFIX, aplimit=500, **cont)
        titles += [p["title"] for p in data["query"]["allpages"]]
        if "continue" not in data:
            break
        cont = data["continue"]
    return [t for t in titles if t.count("/") == 2]


def _query_pages(titles):
    """prop=info|revisions (wikitext) for up to BATCH titles; title -> page dict.

    When the response would be too large the API returns content for only
    some pages plus `continue`; follow it until every page has its revision."""
    out, cont = {}, {}
    while True:
        data = _api(action="query", titles="|".join(titles), prop="info|revisions",
                    rvprop="ids|content", rvslots="main", **cont)
        for p in data["query"].get("pages", []):
            if p["title"] in out and not p.get("revisions"):
                continue
            out[p["title"]] = p
        if "continue" not in data:
            return out
        cont = data["continue"]


def _wikitext(page):
    revs = page.get("revisions") or []
    return revs[0]["slots"]["main"].get("content", "") if revs else ""


_PAGES_TAG = re.compile(r"<pages\b([^>]*?)/?>", re.S | re.I)
_ATTR = re.compile(r"""(\w+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s/>]+))""")


def _spans(wikitext):
    """The <pages index=... from=X to=Y onlysection=... /> transclusions of a page."""
    out = []
    for m in _PAGES_TAG.finditer(wikitext):
        attrs = {a.lower(): (b or c or d) for a, b, c, d in _ATTR.findall(m.group(1))}
        if "index" not in attrs:
            continue
        try:
            first = int(attrs.get("from") or attrs.get("include", "").split("-")[0])
            last = int(attrs.get("to") or first)
        except ValueError:
            continue
        out.append({"index": attrs["index"], "from": first, "to": last,
                    **{k: attrs[k] for k in ("onlysection", "fromsection", "tosection") if k in attrs}})
    return out


# Templates whose content is page furniture rather than text.
_FURNITURE = {"ספר חול", "ספר", "ש", "מרכז", "הערות שוליים", "הערה"}


def _inline_text(wikitext):
    """Text typed directly on the sage page (without the header template,
    transclusions and categories)."""
    code = mwparserfromhell.parse(_PAGES_TAG.sub(" ", wikitext))
    for tpl in code.filter_templates(recursive=False):
        if str(tpl.name).strip() in _FURNITURE:
            code.remove(tpl)
    return _plain(str(code))


def _plain(wikitext):
    """Readable text of a wikitext fragment. Templates are reduced to their
    first parameter ({{קיצור|ת"ח|תלמיד חכם}} -> ת"ח), links to their label."""
    wikitext = re.sub(r"^\s*=+[^=\n]*=+\s*$", "", wikitext, flags=re.M)
    code = mwparserfromhell.parse(wikitext)
    for link in code.filter_wikilinks():
        if str(link.title).strip().startswith(("קטגוריה:", "Category:", "קובץ:", "File:")):
            try:
                code.remove(link)
            except ValueError:
                pass
    for tpl in code.filter_templates(recursive=False):
        try:
            name = str(tpl.name).strip()
            keep = "" if name in _FURNITURE or not tpl.params else _plain(str(tpl.params[0].value))
            code.replace(tpl, keep)
        except ValueError:
            pass
    text = code.strip_code(normalize=True, collapse=True)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean(text)


def _clean(text):
    text = text.translate(BIDI)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# Section markers: <קטע התחלה=ר' אבא בר זבדא/> (names may contain quotes,
# so an unquoted value runs up to "/>").
_MARKER = re.compile(r"""<(?:קטע|section)\s+(התחלה|סוף|begin|end)\s*[=-]\s*(?:"([^"]*)"|([^>]*?))\s*/>""", re.I)


def _section_key(name):
    name = name.translate(BIDI).replace("׳", "'").strip()
    if len(name) > 2 and name[0] == name[-1] == "'":
        name = name[1:-1]  # <קטע התחלה='חכמי אוה"ע'/>
    return " ".join(name.replace('"', "").split())


def _section(scan_texts, span, alt_name=None):
    """Raw wikitext of a transcluded span: pages from..to joined and cut to
    `onlysection` (or fromsection/tosection). None when no scan page exists;
    "" when the named section is not marked on the pages.

    When the exact section name is not marked (a typo on either side, e.g.
    onlysection="אבא אוריין" vs marker "אבא אוריין איש ציידין"), falls back
    to a marker named like the page (`alt_name`) or the single marker that
    starts with the requested name. Wikisource itself shows such a page empty,
    but the text is in the book, so it is used (flagged by the caller)."""
    pages = [scan_texts.get(n) for n in range(span["from"], span["to"] + 1)]
    if all(p is None for p in pages):
        return None
    text = "\n".join(re.sub(r"<noinclude>.*?</noinclude>", "", p or "", flags=re.S) for p in pages)
    begin_name = span.get("onlysection") or span.get("fromsection")
    end_name = span.get("onlysection") or span.get("tosection")
    markers = [(m.start(), m.end(), m.group(1) in ("התחלה", "begin"), _section_key(m.group(2) or m.group(3)))
               for m in _MARKER.finditer(text)]
    start, stop = 0, len(text)
    if begin_name:
        hits = [e for s, e, is_begin, k in markers if is_begin and k == _section_key(begin_name)]
        if not hits:
            begins = {k for s, e, is_begin, k in markers if is_begin}
            want = _section_key(begin_name)
            guess = [k for k in begins if alt_name and k == _section_key(alt_name)]
            guess = guess or [k for k in begins if re.fullmatch(re.escape(want) + r" ?\d+", k)]
            guess = guess or [k for k in begins if k.startswith(want + " ") or want.startswith(k + " ")]
            if len(guess) != 1:
                return ""
            if end_name == begin_name:
                end_name = guess[0]
            begin_name = guess[0]
            hits = [e for s, e, is_begin, k in markers if is_begin and k == guess[0]]
        start = hits[0]
    if end_name:
        hits = [s for s, e, is_begin, k in markers
                if not is_begin and k == _section_key(end_name) and s >= start]
        if hits:
            # onlysection spanning pages has one end marker per page; take the last.
            stop = hits[-1] if span["to"] > span["from"] else hits[0]
    return _MARKER.sub(" ", text[start:stop])


def _scan_title(index_name, n):
    return f"עמוד:{index_name}/{n}"


def _read_json(name, default):
    path, _ = raw_path(NAME, name)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(name, data, indent=1):
    path, _ = raw_path(NAME, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=indent), encoding="utf-8")


def refresh_index():
    """Re-list all sage pages with their metadata and transcluded scan pages.

    index.json = {"retrieved", "version", "titles": [...], "pages": [record...]}
    where a record has title, pageid, revid, length (bytes of the page's own
    wikitext - small for transcluding pages, see section_chars), redirect,
    redirect_target, missing, spans (the <pages> transclusions) and
    inline_text (text typed on the page itself).
    scans.json = {scan page title: {"revid", "quality", "text"}}: the wikitext
    of every "עמוד:" page the sage pages transclude. Only scan pages whose
    revision changed since the last refresh are downloaded again.

    Requests (each delayed by http_json): a few for the listing, ~110 for the
    sage pages (Hebrew titles hit the URI limit before 50 per batch), a few
    for redirect targets, then ~one per 50 scan pages for revision ids and
    one per changed batch for their text."""
    titles = _list_titles()
    records = []
    for batch in _batches(titles):
        pages = _query_pages(batch)
        for title in batch:
            page = pages.get(title, {})
            wikitext = _wikitext(page)
            records.append({
                "title": title, "pageid": page.get("pageid"),
                "revid": (page.get("revisions") or [{}])[0].get("revid"),
                "length": page.get("length", 0), "redirect": bool(page.get("redirect")),
                "redirect_target": None, "missing": bool(page.get("missing")),
                "spans": _spans(wikitext),
                "inline_text": "" if page.get("redirect") else _inline_text(wikitext),
            })

    redirects = [r["title"] for r in records if r["redirect"]]
    targets = {}
    for batch in _batches(redirects):
        data = _api(action="query", titles="|".join(batch), redirects=1)
        targets.update({r["from"]: r["to"] for r in data["query"].get("redirects", [])})
    for r in records:
        r["redirect_target"] = targets.get(r["title"])

    # Scan pages (namespace "עמוד") that hold the transcluded text.
    wanted = sorted({_scan_title(s["index"], n) for r in records for s in r["spans"]
                     for n in range(s["from"], s["to"] + 1)})
    old = _read_json("scans.json", {})
    current = {}
    for batch in _batches(wanted):
        data = _api(action="query", titles="|".join(batch), prop="info")
        current.update({p["title"]: p.get("lastrevid") for p in data["query"].get("pages", [])
                        if not p.get("missing")})
    scans = {t: old[t] for t, rev in current.items() if t in old and old[t].get("revid") == rev}
    for batch in _batches([t for t in current if t not in scans]):
        for title, page in _query_pages(batch).items():
            if page.get("missing"):
                continue
            text = _wikitext(page)
            m = re.search(r'<pagequality\s+level="?(\d)', text)
            scans[title] = {"revid": (page.get("revisions") or [{}])[0].get("revid"),
                            "quality": int(m.group(1)) if m else None, "text": text}

    _write_json("scans.json", scans, indent=0)
    _write_json("index.json", {"retrieved": date.today().isoformat(), "version": INDEX_VERSION,
                               "titles": titles, "pages": records})
    _CACHE.clear()
    return titles


_CACHE = {}


def _load():
    """(index data, {pageid: section text}) with section fields filled in:
    scan_found (some transcluded scan page exists), scan_quality (lowest
    proofreading level 0-4 of those pages) and section_chars."""
    if "data" in _CACHE:
        return _CACHE["data"], _CACHE["texts"]
    data = _read_json("index.json", {})
    if data.get("version") != INDEX_VERSION:
        refresh_index()
        data = _read_json("index.json", {})
    scans = _read_json("scans.json", {})
    texts = {}
    for r in data["pages"]:
        parts, levels, found = [], [], False
        for s in r["spans"]:
            got = {n: scans.get(_scan_title(s["index"], n)) for n in range(s["from"], s["to"] + 1)}
            levels += [g["quality"] for g in got.values() if g and g["quality"] is not None]
            raw = _section({n: g["text"] for n, g in got.items() if g}, s, r["title"].split("/", 2)[2])
            if raw is not None:
                found = True
                parts.append(_plain(raw))
        text = "\n\n".join(p for p in parts if p)
        r["scan_found"] = found
        r["scan_quality"] = min(levels, default=None)
        r["section_chars"] = len(text)
        if text and r["pageid"]:
            texts[str(r["pageid"])] = text
    _CACHE.update(data=data, texts=texts)
    return data, texts


def _load_index():
    return _load()[0]


def index():
    """All sage page titles (kept for backward compatibility)."""
    path, _ = raw_path(NAME, "index.json")
    if not path.exists():
        return refresh_index()
    return json.loads(path.read_text(encoding="utf-8"))["titles"]


def sections():
    """pageid (str) -> plain text of the page's transcluded section."""
    return _load()[1]


def page_text(record, texts=None):
    """Best available plain text of a page: its section, else its own text."""
    texts = sections() if texts is None else texts
    return texts.get(str(record.get("pageid")), "") or record.get("inline_text", "")


def index_entries():
    """The records of refresh_index, each with `kind` (see classify) and the
    title fields of parse_title (name, aliases, qualifier, era)."""
    data, texts = _load()
    out = []
    for r in data["pages"]:
        fields = parse_title(r["title"])
        out.append({**r, **fields, "kind": classify(r, page_text(r, texts), fields)})
    return out


# ---------------------------------------------------------------------------
# Classification

# Section text below this many characters counts as no text at all.
MIN_TEXT = 6

# A cross reference is short: "ערך אבא גוריון איש צידן.", "בערך רב.",
# "עיין ר' יוסי בן חלפתא". Longer texts that start this way are kept as bios.
XREF_MAX = 160
_XREF = re.compile(
    r"""^(?:עיין|עיי'|ע'|עי'|ע"ע|עע"|ראה|ראו|בערך|ערך|נזכר\s+בערך|תמצא|
        כמו\s+ש(?:כתבתי|נתבאר)|(?:ש)?נתבאר|מבואר|כן\s+נקרא|
        (?:ו?זה\s+)?הוא(?!\s+(?:היה|אבי|אחי|בן|בנו|שם|נזכר)\b))
        (?:[\s'"]|$)""", re.X)
# "הוא X ..." = "he is X" (another entry) and counts as a pointer, but not
# "הוא היה ..." / "הוא אבי ..." / "הוא שם ...", which open short bios.

# A short text that ends by sending the reader elsewhere: "איש טרייא, ערך
# אושעיא איש טרייא.", "כולם בערך חי"ת ...", "כל ערך רבין תמצא בערך אבין.",
# "... והוא ר' אבא בר אבינא עיין ערכו." ("ועיין ערך X" after a citation is
# a "see also" and does not count: the text contains "נזכר").
XREF_TAIL_MAX = 110
_XREF_TAIL = re.compile(
    r"""(?:(?:^|[\s,])(?:כולם\s+|לקמן\s+|אחר\s+|תמצא\s+)?ב?ערך\s+[^.,]+\.?\s*$
        |^כל\s+(?:ערך|שמות)\s
        |^כולם\s+ב?ערך
        |\bו?הוא\s+[^.]{2,40}?\s+(?:עיין\s+ערכו|כמבואר\s+בערכו)\.?\s*$)""", re.X)
_XREF_TAIL_NOT = re.compile(r"נזכר|בערוך|בסה\"ד|ביוחסין|באוצר|ו(?:עיין|עין|ע')\s+ערך")

# An entry that exists only through a corrupt reading: "נזכר שבת נג:, אבל
# הוא ט"ס וצ"ל ר' יאשיה." It points to the right name, so it counts as xref.
GHOST_MAX = 250
GHOST_WITHIN = 100
_GHOST = re.compile(r"\bהוא\s+/?\s*ט\"ס")

# Titles that announce a collective entry rather than one person:
# "(כל החכמים ששם אביהם היה אבא)", "(אמוראים ששם אביהם חיננא)", "(תואר)".
# "(סתם)" is NOT one: "רבא (סתם)" is the main entry on Rava.
_LIST_TITLE = re.compile(r"\([^)]*(?:\bכל\b|ששם\s+אביהם|\bתואר\b|החכמים|האמוראים|התנאים)[^)]*\)")

# Collective names: "רבנן דקיסרין", "סבי דפומבדיתא", "זקני דרום", "בני גליל".
_GROUP_NAME = re.compile(r"(?:רבנן|חכמי|בני|סבי|זקני|אנשי|דורשי|תלמידי|נחותי|צנועין)(?:\s|$)")

# A patronym page naming a single son counts as a list only when this short.
SINGLE_SON_MAX = 90

# Words that may precede "בר X" without naming a son of X ("בשם בר X", "נקרא בן X").
_NOT_A_HEAD = {"בשם", "נקרא", "סתם", "הוא", "והוא", "כמו", "או", "ואמרי", "לה", "ערך", "בערך", "גם", "ובן", "ובר"}


def _bases(fields):
    """The name(s) of the page without honorifics: 'רב אמי' -> {'אמי'}."""
    out = set()
    for n in [fields["name"], *fields["aliases"]]:
        words = n.split()
        while len(words) > 1 and words[0] in _HONORIFICS:
            words = words[1:]
        if words:
            out.add(" ".join(words))
    return out


def _is_homonym_list(body, fields):
    """True for a page that lists the people whose father bore this name.

    Such pages ("אביי", "חמא", "אמי או רב אמי") read
        [(<biblical namesake>)] <A> בר <name> <source>, <B> בר <name> <source>, ...
    so: the first paragraph that is not a parenthesised aside must open with
    "<up to 3 words> בר/בן/בריה ד<name>", and the text must name at least two
    different sons of <name>."""
    if len(body) > 3000:
        return False
    body = body.replace("׳", "'").replace("״", '"')
    paras = [p.strip() for p in body.split("\n") if p.strip()]
    paras = [p for p in paras if not re.fullmatch(r"\(.*\)\.?", p)]
    if not paras:
        return False
    first = re.sub(r"^(?:ו?מצינו|ו?נמצא|וכן\s+נמצא|ויש)\s+", "", paras[0])
    for base in _bases(fields):
        # Not "בר'": it is usually "ב-ר' X" ("מעשה בר' חנינא" = "a story about R' Hanina").
        son_of = (r"(?:בר\s+|בן\s+|בריה\s+ד(?:ר'\s*|רב\s+)?)" + re.escape(base)
                  + r"(?=[\s.,:;()]|$)")
        if not re.match(r"^(?:\S+\s+){1,3}?(?:\([^)]*\)\s+)?" + son_of, first):
            continue
        # Count items that start a list entry: "[, ]<honorific> <head> [(או X)|או X] בר <name>".
        item = (r"(?:^|[,.;:]\s+|\n)(?:ויש\s+)?(?:(?:ר'|רב|רבי|רבן|מר|אבא)\s+)?(\S+)"
                r"(?:\s+\([^)]*\)|\s+או\s+\S+)?\s+" + son_of)
        heads = {m.group(1) for m in re.finditer(item, body, flags=re.M)} - _NOT_A_HEAD
        # Two different sons; or a one-line page that only names one son and
        # cites him ("גדיש": "ר' יהודה בן גדיש (בזמן ר' אליעזר) עירובין כז.").
        if len(heads) >= 2 or (heads and len(body) <= SINGLE_SON_MAX):
            return True
    return False


def _is_xref(body):
    body = body.replace("׳", "'").replace("״", '"')
    # Skip a leading parenthesised aside such as a biblical namesake.
    paras = [p.strip() for p in body.split("\n") if p.strip()]
    while len(paras) > 1 and re.fullmatch(r"\(.*\)\.?", paras[0]):
        paras = paras[1:]
    text = " ".join(" ".join(paras).split())
    if len(text) < XREF_MAX and _XREF.match(text):
        return True
    if len(text) < XREF_TAIL_MAX and _XREF_TAIL.search(text) and not _XREF_TAIL_NOT.search(text):
        return True
    # The misprint must be the point of the entry: declared early on.
    return len(text) < GHOST_MAX and bool(_GHOST.search(text[:GHOST_WITHIN]))


def classify(record, text, fields=None):
    """kind of a sage page: "redirect" | "empty" | "xref" | "list" | "bio".

    Rules, cheapest first (text = the plain text of the transcluded section,
    or the page's own text when it transcludes nothing):
    1. redirect: the API flags the page as a redirect.
    2. empty: the page is missing or has no text at all (scan page not
       created, or the section is not marked on it).
    3. xref (see _is_xref), after skipping a leading "(biblical namesake)":
       a. short (< XREF_MAX) and opens with a pointer ("ערך ...", "בערך ...",
          "עיין ...", "כן נקרא ...", "הוא <other name> ..."); or
       b. very short (< XREF_TAIL_MAX) and ends with one ("..., ערך X.",
          "והוא X עיין ערכו."), without a citation ("נזכר") of its own; or
       c. a ghost entry (< GHOST_MAX) declared a misprint ("הוא ט"ס וצ"ל X").
    4. empty: fewer than MIN_TEXT characters otherwise.
    5. list: the title's qualifier announces a group ("(כל החכמים ששם אביהם
       היה אבא)", "(תואר)"), the name is collective ("רבנן דקיסרין",
       "סבי דסורא"), or the text is a list of sons of the title name
       (see _is_homonym_list) - typically the bare-name page ("אביי").
    6. bio: everything else. One-line entries ("נזכר ביצה ג:.") are bios of
       barely-attested sages; the length is in the review CSV.
    """
    fields = fields or parse_title(record["title"])
    if record.get("redirect"):
        return "redirect"
    body = text.strip()
    if record.get("missing") or not body:
        return "empty"
    if _is_xref(body):
        return "xref"
    if len(body) < MIN_TEXT:
        return "empty"
    if _LIST_TITLE.search(record["title"].split("/", 2)[2]) or _GROUP_NAME.match(fields["name"]):
        return "list"
    if _is_homonym_list(body, fields):
        return "list"
    return "bio"


# ---------------------------------------------------------------------------
# Titles: name, aliases, qualifier, era

_HONORIFICS = ("ר'", "רבי", "רבן", "רב", "רבינו", "רבנו", "מר")
_PATRONYMIC = ("בר", "בן", "בריה", "ברב", "בר'")
_ERA_RULES = [
    ("savoraim", re.compile(r"סבורא|רבנן\s+סבוראי|רבנן\s+דסבוראי")),
    ("zugot", re.compile(r"\bזוג(?:ות)?\b|\bמהזוגות\b")),
    ("amoraim", re.compile(r"אמורא|\bאמוראי|\bאמ'")),
    ("tannaim", re.compile(r"תנא|\bתנאים\b|ברייתא|בזמן\s+הבית|זמן\s+המשנה")),
]

# Parenthesised words that describe the person rather than spell his name.
_QUALIFIER_WORDS = {"סתם", "תנא", "אמורא", "ירושלמי", "בבלי", "יוחסין", "כינוי", "אחר", "רב", "זקן",
                    "כהן", "נשיא", "שם", "ס\"א", "ראשון", "שני"}
_QUALIFIER_HINT = re.compile(r"תנא|אמורא|דור|בזמן|תלמיד|\bאבי\b|\bאחי|\bבנו\b|אשה|ממונה|חבירו|גורס|לגרסת|בבלי|ירושלמי|ס\"א")


def era_of(qualifier):
    if not qualifier:
        return None
    for era, rx in _ERA_RULES:
        if rx.search(qualifier):
            return era
    return None


def _expand(variant, base):
    """Complete a partial variant from the base name: 'זמינא' with base
    'ר' אבא בר זבינא' -> 'ר' אבא בר זמינא'; 'בר אבא' replaces the
    patronymic; a variant with its own honorific or 3+ words stays as is."""
    words, bwords = variant.split(), base.split()
    if not words or not bwords:
        return variant
    if words[0] in _HONORIFICS:
        return variant
    if words[0] in _PATRONYMIC:
        if words[0] == "ברב":
            words = ["בר", "רב"] + words[1:]
        for i in range(len(bwords) - 1, 0, -1):
            if bwords[i] in _PATRONYMIC:
                return " ".join(bwords[:i] + words)
        return " ".join(bwords + words)
    if len(words) >= 3:
        return variant
    if len(words) == 1 and len(bwords) >= 2:
        return " ".join(bwords[:-1] + words)
    return variant


def _or_variants(name):
    """Split 'L או R [או R2]' into (name, aliases). R is completed from L:
    one word replaces L's last word ('ר' אבא בר זבינא או זמינא'); 'בר X'
    replaces L's patronymic; an honorific or a full 'X בר Y' form stands
    alone; otherwise R's first word is the variant and the rest is a suffix
    shared by both ('אבא אושעיא או הושעיא איש טריא')."""
    pieces = [p.strip() for p in name.split(" או ")]
    left, aliases = pieces[0], []
    lw = left.split()
    for right in pieces[1:]:
        rw = right.split()
        if not rw:
            continue
        if rw[0] in _HONORIFICS or rw[0] in _PATRONYMIC or len(rw) == 1:
            aliases.append(_expand(right, left))
        elif any(w in _PATRONYMIC or w.startswith(("דר'", "דרב")) for w in lw[1:]):
            aliases.append(right)
        else:
            suffix = rw[1:]
            aliases.append(" ".join(lw[:-1] + rw[:1] + suffix))
            left = " ".join(lw + suffix)
    return left, aliases


def _is_variant(inner, before, at_end):
    """Whether a parenthesised part of a title spells the preceding word
    differently ('אבין (רבין) בר חסדא', 'בר סיסי (סיסיי, סוסיי)') rather
    than describing the person ('(תנא)', '(השני)', '(הכהן)', '(סתם)')."""
    if inner in _HONORIFICS:
        return not at_end  # 'בר (רב) עולא', but 'ר' אבא בר איבו (רב)' is a title
    items = [i.strip() for i in re.split(r",|\s+או\s+", inner) if i.strip()]
    if not items or any(len(i.split()) > 2 for i in items) or _QUALIFIER_HINT.search(inner):
        return False
    if items[0].split()[0] in _PATRONYMIC and before not in _PATRONYMIC:
        return False  # 'ר' אמי (בר נתן)': a patronymic note, not a re-spelling
    for i in items:
        w = i.split()
        if w[-1] in _QUALIFIER_WORDS or (w[0].startswith("ה") and len(w[0]) > 3):
            return False
        # A re-spelling resembles the word it replaces ('נדבך'/'נידבה',
        # 'אבין'/'רבין'); an epithet does not ('אבין (נגרא)').
        if difflib.SequenceMatcher(None, before, w[-1]).ratio() < 0.5:
            return False
    return True


def _apply_variant(tokens, i, variant):
    """Replace tokens[i] (the word before a parenthesis) by `variant`."""
    vw = variant.split()
    if vw == [] or i < 0:
        return None
    if len(vw) == 1 and vw[0] in _HONORIFICS:
        return tokens[:i + 1] + vw + tokens[i + 1:]  # 'בר (רב) עולא'
    if vw[0] in _HONORIFICS and i > 0 and tokens[i - 1] in _HONORIFICS:
        return tokens[:i - 1] + vw + tokens[i + 1:]  # 'ר' אדא (או ר' אידא) דקיסרין'
    if vw[0] in _PATRONYMIC and i > 0 and tokens[i - 1] in _PATRONYMIC:
        return tokens[:i - 1] + vw + tokens[i + 1:]  # 'בר אבין (או בר אובא)'
    return tokens[:i] + vw + tokens[i + 1:]


def parse_title(title):
    """name / aliases / qualifier / era from a page title.

    'ר' יהודה הנשיא - רבי - רבינו הקדוש' -> name 'ר' יהודה הנשיא', aliases ['רבי', 'רבינו הקדוש']
    'אבא גוריא, אבא גוריון'              -> name 'אבא גוריא', aliases ['אבא גוריון']
    'ר' אבא בר זבינא או זמינא'          -> aliases ['ר' אבא בר זמינא']
    'אבטולוס (או אבטולמוס) בר ראובן'     -> aliases ['אבטולמוס בר ראובן']
    'אבין (רבין) בר (רב) חסדא'          -> aliases ['רבין בר חסדא', 'אבין בר רב חסדא']
    'אביי (אמורא קדמון בא"י בדור השני)'  -> qualifier 'אמורא קדמון בא"י בדור השני', era 'amoraim'
    A trailing book index ('רב אידי בר אבין א)') is dropped from the name.
    """
    tail = _clean(title.split("/", 2)[2]).replace("׳", "'").replace("״", '"')
    tail = re.sub(r"\s+[א-י]'?\)\s*$", "", tail)  # "א)", "ב)": the book's own numbering
    qualifiers, variants, tokens = [], [], []
    # Walk the title, keeping the words outside parentheses and remembering,
    # for each variant in parentheses, which kept word it re-spells.
    for m in re.finditer(r"\(([^)]*)\)|[^\s()]+", tail):
        if m.group(1) is None:
            tokens.append(m.group(0))
            continue
        inner = " ".join(m.group(1).split())
        if inner.startswith("או "):
            alt = inner[3:].strip()
            aw = alt.split()
            if len(aw) > 2 and not any(w in _PATRONYMIC for w in aw):
                alt = aw[0]  # '(או אבונא ובבבלי לפעמים רבינא)' -> 'אבונא'
            variants.append((len(tokens) - 1, alt))
        elif tokens and _is_variant(inner, tokens[-1], not tail[m.end():].strip()):
            for alt in re.split(r",|\s+או\s+", inner):
                variants.append((len(tokens) - 1, alt.strip()))
        else:
            qualifiers.append(inner)

    bare = " ".join(tokens)
    # Variants are separated by " - ", "," or an en dash (written as an escape).
    parts = [p.strip() for p in re.split(r"\s+-\s+|\s*,\s*|\s*[\u2013]\s*", bare) if p.strip()]
    first = parts[0] if parts else bare
    first = re.sub(r"\s+[א-י]'$", "", first)  # "ר' צדוק א', ב', ג'"
    first_len = len(first.split())
    aliases = []
    for i, alt in variants:
        if i < first_len:
            new = _apply_variant(first.split(), i, alt)
            if new:
                aliases.append(_or_variants(" ".join(new))[0])
    name, or_aliases = _or_variants(first)
    aliases = or_aliases + aliases
    for p in parts[1:]:
        p = re.sub(r"^ו?(?:ב)?(?:ירושלמי|בבלי)\s+", "", p)
        if re.fullmatch(r"[א-ת]'", p):
            continue  # "ר' צדוק א', ב', ג'"
        aliases.append(_expand(p, name))
    aliases = list(dict.fromkeys(a for a in aliases if a and a != name))
    qualifier = "; ".join(qualifiers) or None
    return {"title_tail": bare, "name": name, "aliases": aliases,
            "qualifier": qualifier, "era": era_of(qualifier)}


def people():
    """One dict per page of kind "bio" (see the module docstring for fields)."""
    return [{"key": f"{NAME}:{e['pageid']}", "source": NAME, "pageid": e["pageid"], "title": e["title"],
             "name": e["name"], "aliases": e["aliases"], "qualifier": e["qualifier"], "era": e["era"]}
            for e in index_entries() if e["kind"] == "bio"]


# ---------------------------------------------------------------------------
# Lookup and full-page download

def _norm(name):
    name = name.replace("׳", "'").translate(BIDI)
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"^(רבי|רבן|ר'|רב|רבינו|רבנו)\s+", "", name.strip())
    name = re.sub(r"\s+(בן|בר)\s+", " ב ", name)
    return " ".join(name.split())


def candidates(names, limit=4):
    """Sage pages whose name matches one of `names` (exact after normalising
    titles like ר'/רבי and בן/בר), best first."""
    keys = {_norm(n) for n in names if n and len(_norm(n)) >= 2}
    out = []
    for title in index():
        sage = title.split("/", 2)[2]
        variants = {_norm(v) for v in re.split(r"\s+-\s+|,\s*|\s+או\s+", sage)} | {_norm(sage)}
        if keys & variants:
            # Prefer the plain page ("אביי") over qualified ones ("אביי (בר כייליל הכהן)").
            out.append((("(" in sage, len(sage)), title))
    out.sort()
    return [t for _, t in out[:limit]]


def fetch(title):
    data = http_json(f"{API}?" + urllib.parse.urlencode({
        "action": "parse", "page": title, "prop": "text|revid", "redirects": 1,
        "format": "json", "formatversion": 2}))["parse"]
    meta = {
        "title": data["title"],
        "requested_title": title, "pageid": data["pageid"], "revid": data["revid"],
        "url": f"{SITE}/wiki/{quote_title(data['title'])}", "retrieved": date.today().isoformat(),
    }
    html_path, html_rel = raw_path(NAME, f"{data['pageid']}.html")
    meta_path, _ = raw_path(NAME, f"{data['pageid']}.meta.json")
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(data["text"], encoding="utf-8")
    meta_path.write_text(json.dumps({**meta, "raw": html_rel}, ensure_ascii=False, indent=1), encoding="utf-8")
    return meta


def ensure(titles):
    """Download the pages that are not saved yet."""
    for title in titles:
        if load_by_title(title)[0] is None:
            fetch(title)


def load_by_title(title):
    """(meta, text) of a page: from its saved HTML snapshot if there is one,
    else from the transcribed scans already in scans.json. (None, None) if
    neither has text."""
    folder, _ = raw_path(NAME, "")
    if folder.exists():
        for meta_path in folder.glob("*.meta.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if title in (meta["title"], meta.get("requested_title")):
                html = (folder / f"{meta['pageid']}.html").read_text(encoding="utf-8")
                return meta, html_to_text(html)
    data, texts = _load()
    for r in data["pages"]:
        if r["title"] == title:
            text = page_text(r, texts)
            if not text:
                return None, None
            _, scans_rel = raw_path(NAME, "scans.json")
            return {"title": r["title"], "pageid": r["pageid"], "revid": r["revid"],
                    "url": f"{SITE}/wiki/{quote_title(r['title'])}", "raw": scans_rel}, text
    return None, None


class _Text(HTMLParser):
    SKIP_TAGS = {"style", "script", "table", "sup"}
    SKIP_CLASSES = {"mw-editsection", "pagenum", "reference", "references", "mw-references-wrap", "noprint"}
    BLOCKS = {"p", "div", "br", "li", "h2", "h3", "h4", "dd"}
    VOID = {"br", "img", "hr", "meta", "link", "wbr", "input"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.out = [], []

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            if tag == "br":
                self.out.append("\n")
            return
        classes = set((dict(attrs).get("class") or "").split())
        self.stack.append(tag in self.SKIP_TAGS or bool(classes & self.SKIP_CLASSES))
        if tag in self.BLOCKS:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if self.stack:
            self.stack.pop()
        if tag in self.BLOCKS:
            self.out.append("\n")

    def handle_data(self, data):
        if not any(self.stack):
            self.out.append(data)


def html_to_text(html):
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.out).replace("[עריכה]", "")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


if __name__ == "__main__":
    print(len(refresh_index()), "sage pages")
