"""Shared HTTP helpers and paths for all source adapters."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

USER_AGENT = "personal-biographies-project/0.1 (educational, personal use)"

# Polite delay between requests to the same host, in seconds.
REQUEST_DELAY = 1.0


def http_get(url, accept="application/json", retries=5):
    """GET with a polite delay and exponential back-off on 429/5xx."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    for attempt in range(retries):
        time.sleep(REQUEST_DELAY)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                retry_after = err.headers.get("Retry-After", "")
                time.sleep(int(retry_after) + 1 if retry_after.isdigit() else 5 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"unreachable: {url}")


def http_json(url):
    return json.loads(http_get(url))


def quote_title(title):
    return urllib.parse.quote(title.replace(" ", "_"), safe="")


def raw_path(provider, name):
    """Path of a raw snapshot file, and its repo-relative form for entries."""
    path = RAW / provider / name
    return path, path.relative_to(ROOT).as_posix()
