"""Wikidata structured facts (CC0 - no attribution required)."""

import json
import urllib.parse
from datetime import date

from .common import http_json, raw_path

NAME = "wikidata"
CREDIT = "wikidata"

API = "https://www.wikidata.org/w/api.php"

# Property id -> field name in the facts dict.
PROPS = {
    "P569": "birth_date",
    "P570": "death_date",
    "P19": "birth_place",
    "P20": "death_place",
    "P119": "burial_place",
    "P22": "father",
    "P25": "mother",
    "P26": "spouse",
    "P40": "child",
    "P3373": "sibling",
    "P1066": "student_of",
    "P802": "student",
    "P800": "notable_work",
    "P106": "occupation",
    "P39": "position_held",
    "P1449": "nickname",
    "P742": "pseudonym",
}

def _entities(ids, props):
    out = {}
    ids = list(ids)
    for i in range(0, len(ids), 50):
        params = urllib.parse.urlencode({
            "action": "wbgetentities", "ids": "|".join(ids[i:i + 50]), "props": props,
            "languages": "he|en", "format": "json",
        })
        out.update(http_json(f"{API}?{params}").get("entities", {}))
    return out


def _label(entity):
    labels = entity.get("labels", {})
    for lang in ("he", "en"):
        if lang in labels:
            return labels[lang]["value"]
    return None


def _time(value):
    """Wikidata time value -> (year, precision). Negative years are BCE."""
    t = value["time"]
    year = int(t[: t.index("-", 1)])
    return {"year": year, "precision": value["precision"], "raw": t, "calendar": value["calendarmodel"].rsplit("/", 1)[-1]}


def qid_for_title(title, site="hewiki"):
    """Wikidata id of a Wikipedia page, following redirects. None if unknown."""
    params = urllib.parse.urlencode({
        "action": "wbgetentities", "sites": site, "titles": title, "props": "sitelinks",
        "sitefilter": site, "redirects": "yes", "format": "json",
    })
    for key, entity in http_json(f"{API}?{params}").get("entities", {}).items():
        if key.startswith("Q") and "missing" not in entity:
            return key, entity.get("sitelinks", {}).get(site, {}).get("title", title)
    return None, title


def fetch_many(qids):
    """Raw snapshots {qid: snapshot}: wbgetentities data plus labels of linked items."""
    entities = _entities(qids, "claims|labels|aliases|descriptions|sitelinks")
    linked = set()
    for entity in entities.values():
        # Keep the repository small: only the properties we use, without references.
        entity["sitelinks"] = {k: v for k, v in entity.get("sitelinks", {}).items() if k == "hewiki"}
        entity["claims"] = {
            pid: [{k: v for k, v in c.items() if k != "references"} for c in claims]
            for pid, claims in entity.get("claims", {}).items() if pid in PROPS or pid == "P31"
        }
        for claims in entity["claims"].values():
            for claim in claims:
                dv = claim.get("mainsnak", {}).get("datavalue", {})
                if dv.get("type") == "wikibase-entityid":
                    linked.add(dv["value"]["id"])
    labels = {k: _label(v) for k, v in _entities(linked, "labels").items()} if linked else {}
    out = {}
    for qid in qids:
        entity = entities.get(qid)
        if not entity or "missing" in entity:
            continue
        refs = {dv["value"]["id"] for cl in entity["claims"].values() for c in cl
                for dv in [c.get("mainsnak", {}).get("datavalue", {})] if dv.get("type") == "wikibase-entityid"}
        out[qid] = {
            "id": qid,
            "url": f"https://www.wikidata.org/wiki/{qid}",
            "retrieved": date.today().isoformat(),
            "entity": entity,
            "linked_labels": {k: labels.get(k) for k in sorted(refs)},
        }
    return out


def save(qid, raw):
    path, rel = raw_path(NAME, f"{qid}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**raw, "raw": rel}, ensure_ascii=False, indent=1), encoding="utf-8")


def load(qid):
    path, _ = raw_path(NAME, f"{qid}.json")
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def facts(raw):
    """Parsed facts from a raw snapshot, for the writer's brief."""
    entity = raw["entity"]
    out = {}
    for pid, field in PROPS.items():
        values = []
        for claim in entity.get("claims", {}).get(pid, []):
            snak = claim.get("mainsnak", {})
            if snak.get("snaktype") != "value" or claim.get("rank") == "deprecated":
                continue
            dv = snak["datavalue"]
            if dv["type"] == "wikibase-entityid":
                qid = dv["value"]["id"]
                values.append({"id": qid, "label": raw["linked_labels"].get(qid)})
            elif dv["type"] == "time":
                values.append(_time(dv["value"]))
            elif dv["type"] == "monolingualtext" and dv["value"]["language"] in ("he", "yi", "arc"):
                values.append({"text": dv["value"]["text"]})
        if values:
            out[field] = values
    return {
        "id": raw["id"],
        "label": _label(entity),
        "description": entity.get("descriptions", {}).get("he", {}).get("value"),
        "aliases": [a["value"] for a in entity.get("aliases", {}).get("he", [])],
        "facts": out,
    }
