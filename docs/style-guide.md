# Biography Writing Guide

This guide is the contract for every entry written into `data/entries/<id>.json`.
Entries are short, fixed-format biographical cards for yeshiva students -
not encyclopedia articles. All entry *content* is written in Hebrew, in
yeshivish / Haredi register. Field names stay in English.

The JSON shape (claims with provenance) is defined in `docs/data-model.md`
and `schema/biography.schema.json`. This guide covers *what* to write.

## 1. Golden rules

1. **Source-bound.** Every fact must appear in the brief (`data/briefs/<id>.md`).
   Never add facts from memory, even well-known ones. If the brief does not
   state it, leave the field empty (`null` / `[]`). An empty field is always
   better than a guess.
2. **Rewrite, don't copy.** Compose new sentences. Do not paste sentences from
   the article. Short fixed terms (book titles, names, quotes such as
   "ממשה עד משה לא קם כמשה") are fine.
3. **Short.** The whole card should be readable in under a minute.
4. **Respectful.** Write as one writes about Gedolei Yisrael in a yeshiva
   publication.
5. **Attributed.** Every claim lists in `src` every provider whose section of
   the brief supports it (`wikipedia`, `wikidata`, `seder_hadorot_segron`, later
   `hamichlol`). If the same fact appears in two sources, list both - this is
   what lets it survive if one source is removed later. Use `editorial` only
   for conventions you apply yourself (honorific, customary title form).
   Never list a provider that does not actually support the value.
   A provider is listed only if it supports the *whole* value: if the article
   gives "י"ד בניסן ד'תתצ"ה" and Seder HaDorot only the year, either use the
   year alone with both providers, or the full date with the article only.

## 2. Register and terminology

Write in a yeshivish / Haredi register:

| Instead of (academic / secular) | Write |
|---|---|
| "הרב משה בן מימון היה פילוסוף ורופא" | "רבינו משה בן מימון, מגדולי הפוסקים בכל הדורות" |
| "על פי המחקר", "חוקרים סבורים", "היסטוריונים" | omit the attribution; state the fact plainly or omit it |
| "אגדה", "מסורת מאוחרת", "דמות מיתולוגית / היסטורית" | "מסופר", "כמובא בחז"ל", or omit |
| "לפנה"ס", "לספירה" | Hebrew year only for pre-CE figures |
| "מת" | "נפטר" / "נסתלק" (חסידות) / "נלקח לבית עולמו" |
| "כתב ספר" | "חיבר" |
| "לימד" | "הרביץ תורה", "העמיד תלמידים הרבה" (when the source supports it) |
| "התנגד ל..." (polemics) | omit unless central; then "נחלק על", "יצא נגד" respectfully |

- Hebrew dates come first. Gregorian year in parentheses after it, for
  figures after year 1 CE only: `ד'תתצ"ח (1138)`.
- Biblical criticism, academic authorship doubts, critical dating of Tanach
  or Chazal, and similar framing are never included.
- Personal controversies, political disputes, scandals and internal
  community conflicts are omitted unless they are the main thing the figure is
  known for. Then mention them in one neutral, respectful clause.
- Secular attainments (philosophy, medicine, science, poetry) may be mentioned
  briefly, after the Torah side.
- Do not include living people's personal details. (No living people are
  expected in this project. If one appears, flag it in `review.flags`.)

## 3. Names and honorifics

- `name`: the name as customary in the beit midrash, with the customary
  leading title:
  - Mikra: "משה רבינו", "שמואל הנביא", "ישעיהו הנביא", "עזרא הסופר".
  - Zugot, Tannaim, Amoraim, Geonim: the name as it appears in Chazal / the
    Geonic literature: "הלל הזקן", "רבי עקיבא", "אביי", "רב סעדיה גאון".
    No trailing honorific.
  - Rishonim: "רבינו משה בן מימון", "רבי שלמה יצחקי". The popular
    acronym goes in `known_as`.
  - Acharonim and Acharonei Zmanenu: "רבי יוסף קארו",
    "הגאון רבי עקיבא איגר", "רבי ישראל מאיר הכהן מראדין". Use "מרן" only
    where it is the customary epithet (e.g. "מרן הבית יוסף").
- `known_as`: acronyms and book-names by which he is called
  ("הרמב"ם", "הנשר הגדול", "החפץ חיים"). Most common first. Max 4.
- `honorific`: displayed after the name.
  - Mikra, Zugot, Tannaim, Amoraim, Savoraim, Geonim: `null`.
  - Rishonim, Acharonim, Acharonei Zmanenu: `"זצ\"ל"`.
  - Chassidic Rebbes and Kabbalists where customary: `"זי\"ע"`.
  - The Arizal: `"ז\"ל"`.

## 4. Fields

Every field below is a claim `{"value": ..., "src": [...]}` (lists are lists
of claims; unknown = `null` or `[]`). See `docs/data-model.md`.

| Field | Content | Limit |
|---|---|---|
| `id` | Wikidata id from the brief | - |
| `sources` | Copy the registry from the brief, keep only providers you cite. For `seder_hadorot_segron`, set `rows` to the `n` of each row you used | - |
| `era` | era key from the brief. `src` = the providers that explicitly place him in that era (e.g. the article says "מגדולי הראשונים", Wikidata occupation "אמוראי בבל"); if none says so explicitly, `["editorial"]`. Fix it if clearly wrong, and flag | - |
| `name`, `known_as`, `honorific` | see section 3 | known_as max 4 |
| `generation` | Tannaim / Amoraim / Geonim only: "תנא בדור השלישי", "אמורא בבל בדור הרביעי", "גאון ישיבת סורא" | short phrase |
| `region` | Main region: "ארץ ישראל", "בבל", "ספרד", "צרפת", "אשכנז", "פולין-ליטא", "צפון אפריקה", "ארצות המזרח" etc. | max 3 |
| `born`, `died` | `{hebrew, gregorian, place}` - each a claim or null. Hebrew date as precise as the source gives ("כ' בטבת ד'תתקס"ה" or "ד'תתצ"ח"). `gregorian` is a year string, null before the Common Era. A competing value from another source goes into `alt`, with its own `src` | - |
| `buried` | Place of burial | - |
| `roles` | Positions: "ראש ישיבת וולוז'ין", "רבה של פראג", "נשיא הסנהדרין" | max 4 |
| `teachers` | Main teachers, customary names | max 5 |
| `students` | Main students | max 5 |
| `family` | `value: {relation, name}`: father, father-in-law, notable sons. Only notable relatives | max 4 |
| `works` | `value: {title, description}` - description up to ~12 words, what the work is | max 6 |
| `mentioned_in` | Mikra / Chazal only: where he appears ("ספר שמואל א'", "מוזכר רבות במשנה ובברייתות") | short phrase |
| `summary` | 2-4 sentences: who he was, why he matters, his main contribution | ~80 words |
| `remember` | One memorable fact, saying, or story for students, from the source | 1 sentence, may be null |
| `review` | `{status: "draft", flags: [...], written: "<date>"}` - every uncertainty, conflict between sources, field the source did not support, or judgement call | - |

## 5. Era adaptations

| Era key | Label | Emphasis | Usually empty |
|---|---|---|---|
| `mikra` | תקופת המקרא | `mentioned_in`, role (נביא, שופט, מלך), main events | `teachers`, `works` (except books of Tanach attributed by Chazal, e.g. "ספר שמואל") |
| `zugot` | אנשי כנסת הגדולה והזוגות | role (נשיא, אב בית דין), sayings in Avot as `remember` | `works`, `buried` |
| `tannaim` | תנאים | `generation`, `region`, teachers / students, `mentioned_in`, a saying from Avot or a famous story | `works` (except attributed works like ספרא, ספר הזוהר) |
| `amoraim` | אמוראים | `generation`, `region` (ארץ ישראל / בבל), academy, famous disputes ("הוויות דאביי ורבא") | `works` |
| `savoraim` | סבוראים | as Amoraim | |
| `geonim` | גאונים | `generation` = academy and years of office, `works` | |
| `rishonim` | ראשונים | `works`, `region`, teachers / students | |
| `acharonim` | אחרונים | `works`, `roles` | |
| `acharonei_zmanenu` | אחרוני זמננו | `roles`, `works`, exact dates | |

## 6. Using the sources in the brief

- **Main article** (Wikipedia; later Hamichlol): the narrative and most facts.
- **Wikidata facts**: dates, places, teachers, works. When they conflict with
  the article, prefer the article and flag it.
- **Seder HaDorot rows**: traditional years from Creation. Rows are matched by
  name only, so first make sure the row really refers to this figure.
  - Mikra through Geonim: prefer Seder HaDorot years when a row clearly
    matches (they follow the traditional count). Do not add a Gregorian year
    unless the main article gives one for the same date.
  - Rishonim onward: prefer the main article's dates; if Seder HaDorot
    differs, keep the article's and add a flag.
  - A Seder HaDorot description ("בעל משנה ברורה") may support
    `known_as` / `works`.
  - Whenever you use a row, cite `seder_hadorot_segron` in the claim's `src` and
    list the row's `n` in `sources.seder_hadorot_segron.rows`.

- **Toldot Tannaim veAmoraim pages** (Zugot, Tannaim, Amoraim, Savoraim):
  Rabbi Aaron Hyman's biographies, written in a traditional Torah voice - the
  preferred source for generation, region, teachers, students, character and
  memorable sayings and stories of Chazal. Pages are matched by name only;
  first confirm the page is about this sage (there are many homonyms, e.g.
  several sages named אביי). Keep in `sources.toldot_tannaim.pages` only the
  pages you used, and cite `toldot_tannaim` in each supported claim. Its
  Talmudic references (e.g. "ברכות כח:") may be kept briefly in `remember`.

## 7. Entries from a single thin source

Many sages are known only from one Toldot Tannaim veAmoraim page or one
Seder HaDorot row. Their cards are short - that is expected and correct.

- Write only what the source says. A card may have just name, era,
  generation, one or two teachers or relatives, and a one- or two-sentence
  summary. Do not pad.
- `era`: if the brief has no era (common for Toldot pages), determine it from
  the text ("תנא", "אמורא", "בדור השלישי לאמוראי בבל", the sages he quotes or
  who quote him) and cite the provider whose text shows it; if you infer it from
  the people he is linked to, use `["editorial"]` and add a flag.
- `summary` must still be at least one full sentence (the schema needs 20
  characters). For a sage mentioned once in the Talmud, say so: "אמורא שנזכר
  פעם אחת בתלמוד, במסכת ...".
- Toldot text is often unproofread OCR: ignore obvious scanning errors, and
  never quote a garbled passage.
- Seder HaDorot rows for kings and biblical figures: keep to the role and
  years; for kings of Israel and Judah state the kingdom and years of reign.

## 8. Output format

- One file per figure: `data/entries/<id>.json`, UTF-8, `indent=1`, key order as in the example.
- Run `python scripts/validate.py <id> ...` and fix every ERROR; resolve warnings or explain them in `review.flags`.

## 9. Example

`data/entries/Q127398.json` (the Rambam) is the reference entry - match its depth, tone and attribution.
