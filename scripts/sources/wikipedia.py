"""Hebrew Wikipedia adapter (CC BY-SA 4.0).

Note: on filtered networks (e.g. NetFree) `/w/api.php` is blocked; fetch from
an unfiltered network. Already-saved raw snapshots work offline.
"""

from . import mediawiki

NAME = "wikipedia"
CREDIT = "wikipedia"
SITE = "https://he.wikipedia.org"
API = f"{SITE}/w/api.php"


def fetch_many(titles):
    return mediawiki.fetch_pages(API, SITE, titles)


def save(eid, meta, wikitext):
    mediawiki.save(NAME, eid, meta, wikitext)


def load(eid):
    return mediawiki.load(NAME, eid)
