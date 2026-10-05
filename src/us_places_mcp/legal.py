"""Reading a Public Land Survey description as patents, tract books and family papers write it.

A description names a tract by its aliquot parts or lot, its section, its
township and range, and the principal meridian they count from:
``E½NE Sec. 18, T84N R39W, 5th P.M.``. The same tract is written a dozen
ways -- ``E2NE``, ``E 1/2 NE 1/4``, ``the east half of the northeast
quarter`` -- and GLO's own index pads it as ``0840N`` / ``0390W``.

Parsing is a reading of a reading. Every tract keeps its ``raw`` text, and
anything guessed (a section number with no "Sec.", a meridian inferred from
the state) is reported in ``warnings`` rather than silently assumed.

Aliquot parts are written smallest first: ``E½NE`` is the east half *of*
the northeast quarter. They expand to quarter-quarters (40-acre cells
labelled like BLM's ``SECDIVLAB``: ``NENE`` is the NE quarter of the NE
quarter). Anything finer than a quarter-quarter is located to the
quarter-quarter that contains it, with a warning.
"""

from __future__ import annotations

import re

from .tables import MERIDIANS, STATE_MERIDIANS, meridian_code, state_code

QUARTERS = ("NE", "NW", "SE", "SW")
HALVES = {"N": ("NE", "NW"), "S": ("SE", "SW"), "E": ("NE", "SE"), "W": ("NW", "SW")}

_WORDS = [
    (r"\bnorth\s*east\b", "NE"),
    (r"\bnorth\s*west\b", "NW"),
    (r"\bsouth\s*east\b", "SE"),
    (r"\bsouth\s*west\b", "SW"),
    (r"\bnorth\b", "N"),
    (r"\bsouth\b", "S"),
    (r"\beast\b", "E"),
    (r"\bwest\b", "W"),
    (r"\bhalf\b", "½"),
    (r"\bquarter\b", "¼"),
]

_TOWNSHIP = re.compile(r"\bT(?:wp|ownship|p)?\.?\s*(\d{1,3})(?:\.\d)?\s*([NS])\b", re.IGNORECASE)
_RANGE = re.compile(r"\bR(?:ange|ng|ge)?\.?\s*(\d{1,3})(?:\.\d)?\s*([EW])\b", re.IGNORECASE)
_GLO_PADDED = re.compile(r"\b(\d{3})(\d)([NS])\b[^0-9]{0,6}\b(\d{3})(\d)([EW])\b", re.IGNORECASE)
_BARE_TR = re.compile(r"\b(\d{1,3})\s*([NS])\.?,?\s+(\d{1,3})\s*([EW])\b", re.IGNORECASE)
_SECTION = re.compile(r"\b(?:Sec(?:tion)?s?|S)\.?\s*(\d{1,2})\b", re.IGNORECASE)
_LOTS = re.compile(r"\b(?:Lots?|L)\.?\s*(\d{1,3}(?:\s*(?:,|and|&)\s*\d{1,3})*)\b", re.IGNORECASE)
_MERIDIAN = re.compile(
    r"\b(\d{1,2}(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth)\s*"
    r"(?:P\.?\s*M\.?|Principal(?:\s+Meridian)?|Meridian)",
    re.IGNORECASE,
)
_NAMED_MERIDIAN = re.compile(
    r"\b([A-Z][A-Za-z.&' ]{2,40}?)\s+(?:Principal\s+)?Meridian\b", re.IGNORECASE
)
_ALIQUOT_TOKEN = re.compile(r"([NSEW])(?:½|1/2|2)|(NE|NW|SE|SW)(?:¼|1/4|4)?")
_ALIQUOT_RUN = re.compile(
    r"\b(?:A,\s*)?((?:(?:[NSEW](?:½|1/2|2))|(?:NE|NW|SE|SW)(?:¼|1/4|4)?)+)(?![A-Z0-9])"
)


def _normalise(text: str) -> str:
    out = text.replace("½", "½").replace("¼", "¼")
    for pattern, repl in _WORDS:
        out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
    # "E ½ of the NE ¼" -> "E½NE¼": drop the joining words and spaces inside an aliquot.
    out = re.sub(r"\b(of\s+the|of)\b", " ", out, flags=re.IGNORECASE)
    out = re.sub(r"(?<=[NSEW])\s+(?=½|1/2\b)", "", out)
    out = re.sub(r"(?:(?<=½)|(?<=¼)|(?<=/2)|(?<=/4))\s+(?=[NS][EW]?\b|[EW]\b)", "", out)
    out = re.sub(r"(?<=[NS][EW])\s+(?=¼|1/4\b)", "", out)
    return out


def expand_aliquot(text: str) -> tuple[list[str], list[str]]:
    """Expand one aliquot description into quarter-quarter labels.

    Returns (labels, warnings). ``E½NE`` -> ``["NENE", "SENE"]``. A bare
    quarter (``NE``) gives its four quarter-quarters; a bare half (``E½``)
    gives eight.
    """
    compact = re.sub(r"\s+", "", text.upper()).removeprefix("A,")
    parts: list[tuple[str, str]] = []
    pos = 0
    for m in _ALIQUOT_TOKEN.finditer(compact):
        if m.start() != pos:
            return [], [f"could not read the aliquot part {text!r}"]
        parts.append(("half", m.group(1)) if m.group(1) else ("quarter", m.group(2)))
        pos = m.end()
    if pos != len(compact) or not parts:
        return [], [f"could not read the aliquot part {text!r}"]

    warnings = []
    # Written smallest first; apply largest first: level 0 is the section's quarter.
    levels = list(reversed(parts))
    if len(levels) > 2:
        warnings.append(
            f"{text!r} is finer than a quarter-quarter; located to the quarter-quarter "
            "that contains it"
        )
        levels = levels[:2]
    allowed: list[set[str]] = []
    for kind, value in levels:
        allowed.append(set(HALVES[value]) if kind == "half" else {value})
    big = allowed[0]
    small = allowed[1] if len(allowed) > 1 else set(QUARTERS)
    labels = [q + Q for Q in QUARTERS if Q in big for q in QUARTERS if q in small]
    return labels, warnings


def _meridian(text: str, state: str | None) -> tuple[str | None, list[str]]:
    if m := _MERIDIAN.search(text):
        if code := meridian_code(m.group(0)):
            return code, []
    for m in _NAMED_MERIDIAN.finditer(text):
        words = m.group(1).strip().split()
        # Try the longest tail first: "in Crawford County, Boise" -> "Boise".
        for start in range(len(words)):
            if code := meridian_code(" ".join(words[start:])):
                return code, []
    if state and len(STATE_MERIDIANS.get(state, ())) == 1:
        code = STATE_MERIDIANS[state][0]
        return code, [f"no meridian named; {state} has only the {MERIDIANS[code]}, so assumed"]
    return None, ["no meridian named; give one, or the state, to locate the tract"]


def _township_range(text: str) -> tuple[tuple | None, list[str]]:
    t = _TOWNSHIP.search(text)
    r = _RANGE.search(text)
    if t and r:
        return (int(t.group(1)), t.group(2).upper(), int(r.group(1)), r.group(2).upper()), []
    if m := _GLO_PADDED.search(text):
        return (int(m.group(1)), m.group(3).upper(), int(m.group(4)), m.group(6).upper()), []
    if m := _BARE_TR.search(text):
        return (
            (int(m.group(1)), m.group(2).upper(), int(m.group(3)), m.group(4).upper()),
            ["township and range read without 'T' and 'R' labels"],
        )
    return None, ["no township and range found"]


def _section(text: str, tr_end: int | None) -> tuple[int | None, list[str]]:
    for m in _SECTION.finditer(text):
        n = int(m.group(1))
        if 1 <= n <= 36:
            return n, []
        return None, [f"section {n} is not 1-36"]
    # "SENW No 13 N 17 W 31": a lone number after the range is often the section.
    if tr_end is not None:
        if m := re.match(r"[\s,;.]*(?:Sec\.?\s*)?(\d{1,2})\b", text[tr_end:]):
            n = int(m.group(1))
            if 1 <= n <= 36:
                return n, [f"section {n} read from a bare number after the range"]
    return None, ["no section found"]


def _tr_end(text: str) -> int | None:
    ends = [m.end() for m in (_RANGE.search(text), _GLO_PADDED.search(text)) if m]
    if not ends and (m := _BARE_TR.search(text)):
        ends = [m.end()]
    return max(ends) if ends else None


def parse_tract(raw: str, state: str | None = None) -> dict:
    """Parse one tract: aliquots or lots, section, township, range, meridian."""
    text = _normalise(raw)
    warnings: list[str] = []
    tr, w = _township_range(text)
    warnings += w
    section, w = _section(text, _tr_end(text))
    warnings += w
    meridian, w = _meridian(raw, state)
    warnings += w

    lots: list[int] = []
    if m := _LOTS.search(text):
        lots = [int(n) for n in re.findall(r"\d+", m.group(1))]
    # Search for aliquots only outside the township/range/section/lot text.
    scrub = text
    for pattern in (_TOWNSHIP, _RANGE, _GLO_PADDED, _BARE_TR, _SECTION, _LOTS, _MERIDIAN):
        scrub = pattern.sub(" ", scrub)
    aliquots, cells = [], []
    for m in _ALIQUOT_RUN.finditer(scrub.upper()):
        labels, w = expand_aliquot(m.group(1))
        warnings += w
        if labels:
            aliquots.append(m.group(1))
            cells += [c for c in labels if c not in cells]

    if tr and tr[0] == 0:
        warnings.append("township 0 is not a township number")
    return {
        "meridian_code": meridian,
        "meridian_name": MERIDIANS.get(meridian) if meridian else None,
        "township": f"{tr[0]}{tr[1]}" if tr else None,
        "range": f"{tr[2]}{tr[3]}" if tr else None,
        "section": section,
        "aliquot_parts": aliquots,
        "quarter_quarters": cells,
        "lots": lots,
        "raw": raw.strip(),
        "warnings": warnings,
    }


def parse(text: str, state: str | None = None) -> dict:
    """Parse a description that may hold several tracts, separated by ';' or new lines.

    A tract that names no township and range inherits the previous tract's,
    since patents list several sections of one township that way.
    """
    st = state_code(state) if state else None
    pieces = [p for p in re.split(r"[;\n]+", text or "") if p.strip()]
    tracts = []
    for piece in pieces:
        tract = parse_tract(piece, st)
        if tracts and tract["township"] is None and tracts[-1]["township"]:
            prev = tracts[-1]
            tract["township"], tract["range"] = prev["township"], prev["range"]
            tract["meridian_code"] = tract["meridian_code"] or prev["meridian_code"]
            tract["meridian_name"] = MERIDIANS.get(tract["meridian_code"] or "")
            tract["warnings"] = [
                w for w in tract["warnings"] if not w.startswith(("no township", "no meridian"))
            ] + ["township, range and meridian carried from the tract before"]
        tracts.append(tract)
    return {"state": st, "tracts": tracts}
