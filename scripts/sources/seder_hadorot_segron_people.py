"""People extracted from 'Seder HaDorot HaMekutzar' rows.

`seder_hadorot_segron.load()` gives one row per line of the chronology table. This
module keeps the rows that describe a single person (sages, patriarchs and
matriarchs, kings, judges, nesiim) and splits the free-text note into a
customary name, aliases (acronyms, nicknames, "בעל <work>" forms) and works
(quoted titles).

Parsing is heuristic: the notes are short and fairly regular
('<acronym> <title> <name> <relation ...> "<work>"'), but not uniform.
Run scripts/report_seder_people.py to review the output.

Keys are "seder_hadorot_segron:<n>" where n is the row index in load(). A row that
names two people (a pair of Zugot, "דבורה הנביאה וברק בן אבינועם") yields
"seder_hadorot_segron:<n>" for the first and "seder_hadorot_segron:<n>b" for the second.

Besides the documented fields each person carries:
  years_kind: "life" (born/died as given), "death" (only the death year is
      known), or "reign" / "tenure" (the row gives a term of office: born/died
      stay None and the era comes from the end of the term);
  era_from: "years", or "neighbors" when the row has no year and the era was
      taken from the dated rows around it (the table is chronological).
"""

import re

from . import seder_hadorot_segron

SOURCE = "seder_hadorot_segron"

# Era boundaries, as the last year from Creation that still belongs to the era.
# A person's era is decided by the year of death (or birth + 70 when only the
# birth is known, or the end of a reign / term of office).
ERA_BOUNDS = (
    ("mikra", 3448),       # end of prophecy: death of Ezra and Nehemiah (3448)
    ("zugot", 3768),       # death of Hillel; the source starts the Tannaim at 3768
    ("tannaim", 3980),     # death of Rabbi Yehuda HaNasi (3979), sealing of the Mishna
    ("amoraim", 4260),     # death of Ravina (4260), sealing of the Babylonian Talmud
    ("savoraim", 4349),    # start of the Geonim (4349)
    ("geonim", 4798),      # death of Rav Hai Gaon (4798), end of the Geonim
    # Rishonim end at 5300 (1540 CE) rather than at the expulsion from Spain
    # (5252): late rishonim who died shortly after it (Abarbanel 5268, Ein
    # Yaakov 5276, Mizrachi 5285, Bartenura 5290) stay rishonim, while the
    # Beit Yosef (5335), Rema (5332) and Maharshal (5334) are Acharonim.
    ("rishonim", 5300),
    ("acharonim", 5659),   # up to 1899 CE
)
LAST_ERA = "acharonei_zmanenu"

PERSON_TYPES = {'לידה ופטירת צדיק ז"ל', 'לידת ופטירת צדיקה ז"ל', "לידה ופטירה"}
DEATH_TYPES = {"תאריך פטירה"}
KING_TYPES = {"מלך מישראל", "מלך משבט יהודה", "מלך לא יהודי"}
PERIOD_TYPE = "תקופה"

# Collective or event rows that carry a person icon, and period headings.
EXCLUDE_RE = re.compile(r"בעולם|^מלכות בני |פרס-כורש|הכניע|^רב היה|^נהג |^עסקו |^רבנן |^הגזירה"
                        r"|^תקופת|^בנין |^מלכות בית |:")

# Leading words that make the row a term of office / birth / death of a person.
PREFIXES = ("מלכות", "שלטון", "כהונת", "נציבות", "הולדת", "פטירת")

TITLES = {"רבי", "רב", "ר'", "רבנו", "רבינו", "רבן", "רבנית", "הרב"}
# Titles that may follow an alias block made of plain words ("נימוקי יוסף רבי ...").
OPEN_TITLES = {"רבי", "ר'", "הרב"}
# Honorifics dropped from a leading alias block ("מרן מלכא מורנו הרב רבי ...").
HONORIFICS = {"מרן", "מלכא", "מורנו", "הגאון", "הקדוש", "דון", "הרב"}
# First words of a nickname ("המגיד ממזריטש", "הסבא מקלם", "בבא סאלי").
NICKNAMES = {"המגיד", "החוזה", "היהודי", "הסבא", "המשגיח", "הסטייפלר", "האדמור", 'האדמו"ר',
             "השר", "בבא", "ר'", "רבי", "רב", "הנציב", "בעל"}
# Words that end the name: relations, descriptions, verbs.
STOP_WORDS = {
    "תלמיד", "תלמידו", "תלמידי", "תלמידה", "רבו", "רבם", "אבי", "אביו", "בנו", "נכד", "נכדו",
    "נינו", "חתנו", "חמיו", "גיס", "גיסו", "אחיו", "אחי", "אח", "אחות", "אחיינו", "דודו",
    "מחותנו", "סבו", "אשת", "ובתו", "חבירו", "חברו", "חבר", "בעל", "ראש", "הפרשן", "נחשב",
    "גדול", "מחנכת", "דיין", "פוסק", "מקובל", "זקן", "מיסד", "מייסד", "מגדולי", "מרבני",
    "מרבותיו", "מתלמידי", "מכחמי", "פרנס", "למד", "שלט", "נהיה", "נמשח", "שהרבה", "לבדו",
    "במקביל", "שר", "בגיל", "ככהן", "על", "סידר", "היה", "ונבואת", "וחתימת", "ונפסקה",
    "התאבלו", "שהוא", "מלך", "בבבל", "חכם", "המגיד", "החוזה", "היהודי", "הסבא", "המשגיח",
    "הסטייפלר", "האדמור", 'האדמו"ר', "הנציב",
}
# Relation words: quoted titles after them belong to someone else.
RELATION_WORDS = STOP_WORDS - {"בעל", "על", "המגיד", "החוזה", "היהודי", "הסבא", "המשגיח",
                               "הסטייפלר", "האדמור", 'האדמו"ר', "הנציב", "חכם"} | {"של"}
# Abbreviations that are part of a name rather than an acronym alias.
NAME_ABBREVS = {'ב"ר', 'יו"ט', 'כ"ץ'}
# Acronyms that are titles or blessings, never aliases.
NOT_ALIASES = {'ר"י', 'אב"ד', 'הי"ד', 'שליט"א', 'זצ"ל', 'הרשל"צ', 'ז"ל', 'ע"י', 'אדמו"ר'} | NAME_ABBREVS
# Quoted strings starting with these are book titles even though they are acronyms.
WORK_ACRONYMS = {'שו"ע', 'שו"ת', 'קיצור', 'קצור', 'תוס\''}
# Works whose leading ה belongs to the title ("הלכות קטנות", "הר צבי").
KEEP_HE = {"הלכות", "הגהות", "הר", "הדרת", "היכל", "הליכות", "המעלות"}
# Single-word parenthesis notes that are places, tags or ordinals, not alternative names.
SINGLE_WORD_PLACES = {"צדיק", "גרים", "אושא", "תימן", "פרובנס", "קבלה", "שרייבר", "פולין",
                      "הראשון", "השני", "השלישי"}
MONTH_RE = re.compile(r"ניסן|אייר|סיון|תמוז|אב\b|אלול|תשרי|חשון|כסלו|טבת|שבט|אדר|ר\"ח")
MARK = "¦"          # internal stop marker

NIQQUD_RE = re.compile(r"[֑-ׇ]")
ACRONYM_RE = re.compile(r'[א-ת]"[א-ת]')


def _is_acronym(word):
    return bool(ACRONYM_RE.search(word))


def _normalize(text):
    s = text.replace("''", '"').replace("״", '"').replace("׳", "'").replace("”", '"').replace("“", '"')
    s = NIQQUD_RE.sub("", s)
    s = re.sub(r"ר'(?=[א-ת])", "ר' ", s)
    s = re.sub(r" -(?=[א-ת])", " ", s)      # "בעל -שם" -> "בעל שם"
    s = re.sub(r"\s+,", ",", s)
    return " ".join(s.split())


# ---- parentheses ----------------------------------------------------------

def _paren_notes(content, single_ok):
    """Aliases and works worth keeping from a parenthesis; places and dates are dropped."""
    content = content.strip().strip("'")
    if not content or re.search(r"\d|וי\"א|^ע'|^ספר |^בן |^בעל |^לא ", content) or MONTH_RE.search(content):
        return [], []
    parts = [p.strip().strip("'") for p in content.split(",") if p.strip()]
    aliases, works = [], []
    for p in parts:
        words = p.split()
        first = words[0]
        if p.startswith('שו"ת '):
            works.append(p[5:])
        elif _is_acronym(first) and len(words) <= 2 and first not in NOT_ALIASES:
            aliases.append(p)
        elif first in NICKNAMES or first in {"המאירי"} or p.startswith("הרוגצ"):
            aliases.append(p)
        elif p in {"עקידת יצחק", "דרכי הגמרה"}:
            works.append(p)
        elif single_ok and len(words) <= 2 and p not in SINGLE_WORD_PLACES and len(parts) == 1:
            aliases.append(p)    # an alternative name: "(ינאי)", "(יכניה)", "(שלומציון המלכה)"
    return aliases, works


def _strip_parens(s, kind):
    """Replace each parenthesis by a placeholder word; return (text, notes)."""
    notes, out, i = [], [], 0
    for m in re.finditer(r"\(([^()]*)\)?", s):
        content = m.group(1)
        after = s[m.end():].lstrip()
        inline = (len(content.split()) == 1 and not re.search(r"\d", content)
                  and bool(re.match(r'(בן|בר|ב"ר) ', after)))
        notes.append((inline, _paren_notes(content, inline or kind == "reign")))
        out.append(s[i:m.start()])
        out.append(f" {MARK}{len(notes) - 1} ")
        i = m.end()
    out.append(s[i:])
    return " ".join("".join(out).split()), notes


# ---- tokens ---------------------------------------------------------------

OPEN_RE = re.compile(r"^([הב]?)([\"'])(?=[א-ת])")


def _opens_quote(w):
    m = OPEN_RE.match(w)
    if not m:
        return None
    prefix, quote = m.group(1), m.group(2)
    rest = w[m.end():]
    if prefix and (w in NAME_ABBREVS or len(rest.rstrip("\"',.")) < 2):
        return None          # an acronym like ב"ר, not a quote
    if quote == "'" and not (w.startswith("'") or re.match(r"^ה'[א-ת]{2,}", w)):
        return None
    return m


def _tokens(s):
    """Split into tokens: ('T', word), ('Q', content, glued prefix), ('M',) stop, ('P', i) parenthesis."""
    words = s.split()
    toks, i = [], 0
    while i < len(words):
        w = words[i]
        pm = re.fullmatch(MARK + r"(\d+)", w)
        if pm:
            toks.append(("P", int(pm.group(1))))
            i += 1
            continue
        m = _opens_quote(w)
        if m:
            prefix, quote = m.group(1), m.group(2)
            parts, j, cur = [], i, w[m.end():]
            while True:
                trail = cur.rstrip(",.:")
                if trail.endswith(quote) and (len(trail) > 1 or j > i) and trail != "ר'":
                    parts.append(trail[:-1])
                    j += 1
                    break
                parts.append(cur)
                j += 1
                if j >= len(words) or _opens_quote(words[j]) or words[j].startswith(MARK):
                    break        # never closed, or a new quote opens
                cur = words[j]
            content = " ".join(p for p in parts if p).strip(" .")
            if content:
                toks.append(("Q", content, prefix))
            i = j
            continue
        if w in {"-", "--"} or ".." in w:
            head = w.split("..")[0]
            if head and head != "-":
                toks.append(("T", head))
            toks.append(("M",))
        elif len(w) > 1 and w[-1] in ",.:;":
            toks.append(("T", w.rstrip(",.:;")))
            toks.append(("M",))
        else:
            toks.append(("T", w))
        i += 1
    return toks


# ---- quotes and "בעל" -----------------------------------------------------

def _work_title(content):
    first = content.split()[0]
    if content.startswith("ה") and len(content.split()) > 1 and not _is_acronym(first) and first not in KEEP_HE:
        return content[1:]
    return content


def _classify_quote(content, prefix, after_bal=False):
    """A quoted string -> (aliases, works)."""
    content = content.split(" על ")[0].strip()
    words = content.split()
    if not words:
        return [], []
    first = words[0]
    if first == "בעל" and len(words) > 1:
        return [content], [_work_title(" ".join(words[1:]))]
    if not after_bal:
        nickname = first in NICKNAMES and not (first == "המגיד" and len(words) > 1 and not words[1].startswith("מ"))
        acronym = len(words) <= 2 and _is_acronym(first) and first not in NOT_ALIASES | WORK_ACRONYMS
        if nickname or acronym:
            return [content], []
    works = [_work_title(p.strip()) for p in content.split(",") if p.strip()]
    aliases = ["בעל " + prefix + p.strip() for p in content.split(",") if p.strip()]
    return aliases, works


# ---- name -----------------------------------------------------------------

def _leading_block(toks):
    """Index where the name starts after a leading alias block, or 0."""
    best = 0
    for t in range(1, min(len(toks), 6)):
        tok = toks[t]
        if tok[0] != "T" or tok[1] not in TITLES:
            continue
        pre = toks[:t]
        if any(p[0] not in "TQ" for p in pre):
            break
        special = all(p[0] == "Q" or _is_acronym(p[1]) or p[1] in HONORIFICS or p[1] in TITLES
                      for p in pre if p[0] in "TQ")
        opens = (tok[1] in OPEN_TITLES and t + 1 < len(toks) and toks[t + 1][0] == "T"
                 and not any(p[0] == "T" and p[1] in RELATION_WORDS for p in pre))
        if special or opens:
            best = t
    # Several titles in a row ("הרב רבי"): the name starts at the last one.
    while best and best + 1 < len(toks) and toks[best + 1][0] == "T" and toks[best + 1][1] in TITLES:
        best += 1
    return best


def _parse_name(text, kind):
    """Free text of one person -> (name, aliases, works)."""
    aliases, works = [], []
    s, notes = _strip_parens(_normalize(text), kind)
    toks = _tokens(s)

    def take_paren(idx):
        aliases.extend(notes[idx][1][0])
        works.extend(notes[idx][1][1])

    start = _leading_block(toks)
    words = []
    for tok in toks[:start]:
        if tok[0] == "Q":
            a, w = _classify_quote(tok[1], tok[2])
            aliases.extend(a)
            works.extend(w)
        elif tok[1] not in HONORIFICS and tok[1] not in TITLES:
            words.append(tok[1])
    if words:
        block = " ".join(words)
        if len(words) > 1 and not _is_acronym(words[0]):
            aliases.append("בעל " + block)     # "נימוקי יוסף רבי יוסף חביבה"
            works.append(block)
        else:
            aliases.append(block)

    # The name proper.
    name, k = [], start
    while k < len(toks):
        tok = toks[k]
        if tok[0] == "P" and notes[tok[1]][0]:
            take_paren(tok[1])                 # "רבי רפאל (אהרן) בן שמעון"
            k += 1
            continue
        if tok[0] != "T":
            break
        w = tok[1]
        nxt = toks[k + 1] if k + 1 < len(toks) else None
        nxt_w = nxt[1] if nxt and nxt[0] == "T" else None
        if name:
            if w == "בעל" and nxt_w == "שם":
                name.append(w)                 # "בעל שם (טוב)" is part of the name
                k += 1
                continue
            if w in STOP_WORDS or nxt_w == "של" or re.search(r"\d", w):
                break
            if w in {"בן", "בר", 'ב"ר', "בת", "ברבי"} and (
                    nxt_w is None or nxt_w in TITLES - {"רב"} or nxt_w.startswith("הר'") or re.search(r"\d", nxt_w)):
                break
            if w == "רב" and name[-1] not in {"בר", "בן", "בי"}:
                break
            if w == "גאון" and name[0] == "רבי":
                break
            if _is_acronym(w) and w not in NAME_ABBREVS:
                break
            if re.fullmatch(r"ב?[א-ת]'", w) and w != "ר'":
                break                          # a date: "בז' אדר"
            if len(name) >= 8:
                break
        name.append(w)
        k += 1

    # Right after the name: an acronym or nickname ('המהרי"ל דיסקין', 'המגיד ממזריטש').
    rest = toks[k:]
    if rest and rest[0][0] == "T":
        w = rest[0][1]
        if (_is_acronym(w) and w not in NOT_ALIASES) or w in NICKNAMES - {"בעל", "ר'", "רבי", "רב"}:
            alias = [w]
            if len(rest) > 1 and rest[1][0] == "T" and rest[1][1] not in STOP_WORDS | {"של"} \
                    and not _is_acronym(rest[1][1]) and (len(rest) == 2 or rest[2][0] != "T"
                                                         or rest[1][1].startswith("מ")
                                                         or rest[1][1] in {"הזקן", "האמצעי"}):
                alias.append(rest[1][1])
            aliases.append(" ".join(alias))

    # The rest: parentheses, quoted works and "בעל X", up to a relation word
    # (quoted titles after "תלמיד ..." or "בנו של ..." belong to someone else).
    i = 0
    while i < len(rest):
        tok = rest[i]
        if tok[0] == "T" and tok[1] in RELATION_WORDS:
            break
        if tok[0] == "P":
            take_paren(tok[1])
        elif tok[0] == "Q":
            a, w = _classify_quote(tok[1], tok[2])
            aliases.extend(a)
            works.extend(w)
        elif tok[0] == "T" and tok[1] == "בעל" and i + 1 < len(rest):
            j = i + 1
            if rest[j][0] == "T" and rest[j][1] == "ספר":
                j += 1                          # 'בעל ספר "מזרחי"'
            if j < len(rest) and rest[j][0] == "Q":
                q = rest[j]
                aliases.append("בעל " + q[2] + q[1])
                if _is_acronym(q[1]) and len(q[1].split()) == 1:
                    aliases.append(q[2] + q[1])     # 'בעל "הסמ"ג"' -> also 'הסמ"ג'
                works.extend(_classify_quote(q[1], q[2], after_bal=True)[1])
                i = j + 1
                continue
            phrase = []
            for t2 in rest[i + 1:i + 4]:
                if t2[0] != "T" or t2[1] in STOP_WORDS:
                    break
                phrase.append(t2[1])
                if _is_acronym(t2[1]):
                    break
            if phrase:
                label = " ".join(phrase)
                aliases.append("בעל " + label)
                if _is_acronym(label):
                    aliases.append(label)      # "בעל הט"ז" -> also "הט"ז"
                else:
                    works.append(_work_title(label))
                i += 1 + len(phrase)
                continue
        i += 1

    clean = " ".join(name).strip(" -,'\"")
    return clean, _dedupe(aliases, clean), _dedupe(works, None)


def _dedupe(items, name):
    seen, out = set(), []
    for x in items:
        x = " ".join(x.split()).strip(" ,.-")
        if x and x != name and x not in seen and x not in NOT_ALIASES:
            seen.add(x)
            out.append(x)
    return out


# ---- rows -----------------------------------------------------------------

def era_of(year):
    if year is None:
        return None
    for era, last in ERA_BOUNDS:
        if year <= last:
            return era
    return LAST_ERA


def _split_pair(segment):
    """'יהודה בן טבאי ושמעון בן שטח' -> two names; otherwise one."""
    head = re.split(r"\s[-(]|,", segment)[0]
    words = head.split()
    for k in range(1, len(words)):
        w = words[k]
        if w.startswith("ו") and len(w) > 2 and w[1:] not in {"חתימת", "נפסקה"} and words[k - 1] != "בן":
            return [" ".join(words[:k]), " ".join(words[k:])[1:] + segment[len(head):]]
    return [segment]


def _row_people(row):
    text = _normalize(row["text"])
    rtype = row["type"]
    if not text or EXCLUDE_RE.search(text):
        return []
    if rtype in PERSON_TYPES:
        kind = "life"
    elif rtype in DEATH_TYPES:
        kind = "death"
    elif rtype in KING_TYPES:
        kind = "reign"
    elif rtype == PERIOD_TYPE:
        kind = "tenure"
    else:
        return []

    body, first = text, text.split()[0]
    if first in PREFIXES:
        body = body[len(first):].strip()
        if first == "נציבות":
            kind = "reign"
    elif kind == "tenure":
        # Period rows that are really a person's term: a pair of Zugot or a titled sage.
        zugot = row["section"] == "תקופת הזוגות" and not re.search(r"\d|\"", body) and len(body.split()) <= 6
        titled = first in TITLES and len(body.split("(")[0].split()) <= 8 and not re.search(r"\d", body)
        if not (zugot or titled or body.startswith("אנטיגנוס")):
            return []
    if kind == "death" and first != "פטירת":
        return []
    body = re.sub(r"\s*ובית דינו", "", body)
    if not body:
        return []

    ys = row["years"]
    born = died = None
    if kind == "life" and len(ys) == 2:
        born, died = ys
        if died < born:
            died = None          # a typo in the source (e.g. 5507-5075)
    elif kind in {"life", "death"} and ys:
        died = ys[-1]            # a single year in a life row is the death ("????" birth)
    if kind in {"life", "death"}:
        basis = died if died is not None else (born + 70 if born is not None else None)
        years_kind = "life" if born is not None else "death"
    else:
        basis = max(ys) if ys else None
        years_kind = kind

    parts = _split_pair(body) if kind == "tenure" or first == "פטירת" else [body]
    people = []
    for i, part in enumerate(parts):
        name, aliases, works = _parse_name(part, kind)
        if len(name) < 2:
            continue
        people.append({
            "key": f"{SOURCE}:{row['n']}" + ("b" if i else ""),
            "source": SOURCE,
            "n": row["n"],
            "name": name,
            "aliases": aliases,
            "works": works,
            "era": era_of(basis),
            "born": born,
            "died": died,
            "years_kind": years_kind,
            "era_from": "years" if basis is not None else None,
            "text": row["text"],
        })
    return people


def _fill_eras_from_neighbors(found):
    """Undated rows sit in chronological order: use the era shared by the dated rows around them."""
    for k, p in enumerate(found):
        if p["era"] is not None:
            continue
        before = next((q["era"] for q in reversed(found[:k]) if q["era_from"] == "years"), None)
        after = next((q["era"] for q in found[k + 1:] if q["era_from"] == "years"), None)
        if before and before == after:
            p["era"], p["era_from"] = before, "neighbors"


def people(rows=None):
    rows = rows if rows is not None else seder_hadorot_segron.load()
    found = []
    for row in rows:
        found.extend(_row_people(row))
    _fill_eras_from_neighbors(found)
    return found
