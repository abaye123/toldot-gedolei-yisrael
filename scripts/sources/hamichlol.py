"""Hamichlol adapter - DISABLED until written permission is granted.

Hamichlol's original content belongs to Machon Chochmat HaTorah and is
licensed for personal, non-public use only; its robots.txt also disallows
automated access (`User-agent: *  Disallow: /`) and the API path `/w/`.
Do not enable this adapter until the site grants written permission, then
set `"enabled": true` in `config/sources.json` and fill in the `hamichlol`
credit in `config/credits.json`.

Hamichlol runs MediaWiki, so once enabled it stores the same raw snapshot
(wikitext + meta) as Wikipedia and goes through the same extraction.
"""

import json

from . import mediawiki
from .common import ROOT

NAME = "hamichlol"
CREDIT = "hamichlol"
SITE = "https://www.hamichlol.org.il"
API = f"{SITE}/w/api.php"


def ensure_enabled():
    cfg = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8")).get(NAME, {})
    if not cfg.get("enabled"):
        raise PermissionError(
            "Hamichlol adapter is disabled: written permission from Hamichlol is required "
            "before fetching. See scripts/sources/hamichlol.py."
        )


def fetch_many(titles):
    ensure_enabled()
    out = mediawiki.fetch_pages(API, SITE, titles)
    for result in out.values():
        if isinstance(result, tuple):  # Hamichlol serves pages at the site root
            result[0]["url"] = f"{SITE}/{result[0]['url'].rsplit('/wiki/', 1)[1]}"
    return out


def save(eid, meta, wikitext):
    mediawiki.save(NAME, eid, meta, wikitext)


def load(eid):
    return mediawiki.load(NAME, eid)
