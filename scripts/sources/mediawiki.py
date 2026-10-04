"""Generic MediaWiki access and wikitext extraction.

Shared by every wiki-based source (Hebrew Wikipedia, Hamichlol). The raw
snapshot is the page's wikitext as stored by MediaWiki, plus a meta file with
the revision id, so the exact text used can always be traced and re-derived.
"""

import json
import re
import urllib.parse
from datetime import date

import mwparserfromhell

from .common import http_json, quote_title, raw_path

# Trailing sections that never carry biographical content.
STOP_SECTIONS = {
    "הערות שוליים", "קישורים חיצוניים", "לקריאה נוספת", "ראו גם", "ביבליוגרפיה", "מקורות",
    "סימוכין", "גלריה", "קישורים", "הערות", "לקריאה נוספת ומקורות",
}
# Link namespaces whose links are media / categories, not text.
NON_TEXT_LINKS = re.compile(r"^\s*:?\s*(קובץ|תמונה|file|image|קטגוריה|category|media)\s*:", re.I)
# Infobox parameters that hold media, not facts.
MEDIA_PARAMS = re.compile(r"^(תמונה|כיתוב|image|caption|גודל|רוחב|alt)", re.I)
# Templates that are infoboxes have many named parameters; this is the floor.
INFOBOX_MIN_PARAMS = 4


# Titles per request. MediaWiki allows 50; batching keeps us well inside
# the anonymous rate limits (https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits).
BATCH = 50


def fetch_pages(api, site, titles):
    """Fetch wikitext + metadata for many pages in batched requests.

    Returns {requested title: (meta, wikitext)}; titles that do not exist map
    to a LookupError instance instead.
    """
    out = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        base = {
            "action": "query", "titles": "|".join(chunk), "redirects": 1, "format": "json", "formatversion": 2,
            "prop": "revisions|pageprops", "rvprop": "content|ids|timestamp", "rvslots": "main",
        }
        pages, renames, cont = {}, {}, {}
        while True:  # large batches come back in several parts
            data = http_json(f"{api}?{urllib.parse.urlencode({**base, **cont})}")
            q = data.get("query", {})
            for r in q.get("normalized", []) + q.get("redirects", []):
                renames[r["from"]] = r["to"]
            for page in q.get("pages", []):
                merged = pages.setdefault(page["title"], page)
                if "revisions" in page:
                    merged["revisions"] = page["revisions"]
            if "continue" not in data:
                break
            cont = data["continue"]
        for title in chunk:
            final = title
            while final in renames:
                final = renames[final]
            page = pages.get(final)
            if not page or page.get("missing") or page.get("invalid") or "revisions" not in page:
                out[title] = LookupError(f"page not found: {title}")
                continue
            rev = page["revisions"][0]
            props = page.get("pageprops", {})
            out[title] = ({
                "title": page["title"],
                "requested_title": title,
                "pageid": page["pageid"],
                "revid": rev["revid"],
                "timestamp": rev["timestamp"],
                "url": f"{site}/wiki/{quote_title(page['title'])}",
                "wikidata_id": props.get("wikibase_item"),
                "disambiguation": "disambiguation" in props,
                "retrieved": date.today().isoformat(),
            }, rev["slots"]["main"]["content"])
    return out


def save(provider, eid, meta, wikitext):
    text_path, text_rel = raw_path(provider, f"{eid}.wikitext")
    meta_path, _ = raw_path(provider, f"{eid}.meta.json")
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text(wikitext, encoding="utf-8")
    meta_path.write_text(json.dumps({**meta, "raw": text_rel}, ensure_ascii=False, indent=1), encoding="utf-8")


def load(provider, eid):
    text_path, _ = raw_path(provider, f"{eid}.wikitext")
    meta_path, _ = raw_path(provider, f"{eid}.meta.json")
    if not text_path.exists():
        return None, None
    return json.loads(meta_path.read_text(encoding="utf-8")), text_path.read_text(encoding="utf-8")


# Inline templates whose text belongs to the article: name -> how to render.
QUOTE_TEMPLATES = {"ציטוטון", "ציטוט", "ציטוט-צף", "ציטוט מסגרת"}
TEXT_TEMPLATES = {"מונחון", "כתב מוקטן", "הדגשה", "כתיב", "מרכז"}
CITATION_TEMPLATES = {"בבלי", "ירושלמי", "משנה", "תנ\"ך", "תנך", "תוספתא", "מדרש רבה", "רמב\"ם", "שולחן ערוך"}


def _param(tpl, *names):
    for name in names:
        if tpl.has(name):
            return str(tpl.get(name).value).strip()
    return ""


def _inline_templates(wikicode):
    """Replace text-bearing templates by their text; others are dropped by strip_code."""
    for tpl in wikicode.filter_templates(recursive=False):
        name = str(tpl.name).strip()
        if name in QUOTE_TEMPLATES:
            text = _param(tpl, "תוכן", "1")
            replacement = f'"{text}"' if text else ""
        elif name in TEXT_TEMPLATES:
            replacement = _param(tpl, "1")
        elif name in CITATION_TEMPLATES:
            parts = [str(p.value).strip() for p in tpl.params if not p.showkey]
            replacement = f"({name} {' '.join(parts)})" if parts else ""
        else:
            continue
        inner = mwparserfromhell.parse(replacement)
        _inline_templates(inner)
        try:
            wikicode.replace(tpl, inner)
        except ValueError:
            pass


def _clean(node_text):
    return " ".join(node_text.split())


def _strip(wikicode):
    _inline_templates(wikicode)
    for link in wikicode.filter_wikilinks(recursive=True):
        if NON_TEXT_LINKS.match(str(link.title)):
            try:
                wikicode.remove(link)
            except ValueError:
                pass
    return wikicode.strip_code(normalize=True, collapse=True)


def extract(wikitext):
    """Wikitext -> (plain text with '## ' section headings, infobox [(key, value)])."""
    code = mwparserfromhell.parse(wikitext)

    infobox = []
    for tpl in code.filter_templates(recursive=False):
        named = [p for p in tpl.params if p.showkey]
        if len(named) >= INFOBOX_MIN_PARAMS:
            for p in named:
                if MEDIA_PARAMS.match(_clean(str(p.name))):
                    continue
                value = _clean(_strip(mwparserfromhell.parse(str(p.value))))
                if value and not value.lower().startswith(("קובץ:", "file:")):
                    infobox.append((_clean(str(p.name)), value))
            break

    parts, stopped = [], False
    for section in code.get_sections(flat=True, include_lead=True):
        headings = section.filter_headings(recursive=False)
        if headings:
            title = _clean(_strip(headings[0].title))
            if headings[0].level == 2:
                stopped = title in STOP_SECTIONS
            if stopped:
                continue
            section.remove(headings[0])
            body = _strip(section).strip()
            parts.append(f"## {title}\n{body}" if body else f"## {title}")
        elif not stopped:
            parts.append(_strip(section).strip())
    text = "\n\n".join(p for p in parts if p)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, infobox
