"""From a federal land patent to the case file behind it.

A patent is the end of a process. The land entry case file, at the National
Archives in Record Group 49, holds the application, the receipts and, for a
homestead, the final proof: years of residence, improvements, witnesses who
were often neighbours or kin, and citizenship papers. Which file, and in
which series, depends on the kind of entry, which the patent's *Authority*
names ("May 20, 1862: Homestead EntryOriginal (12 Stat. 392)").

This module reads the authority and returns where the file should be and
the search to run for it. MCP servers cannot call one another, so the
National Archives search comes back as arguments for nara-catalog-mcp's
``search_records_advanced``, not as results.
"""

from __future__ import annotations

import re

from .tables import STATE_NAMES

#: (kind, words that identify it, what the file is, which series family holds it)
ENTRY_TYPES: tuple[tuple[str, tuple[str, ...], str, str], ...] = (
    (
        "homestead",
        ("homestead",),
        "Homestead case file: application, final proof (residence, improvements, two "
        "witnesses), and citizenship or declaration of intention. A cancelled or "
        "relinquished entry has a file too, in a different series.",
        "RG 49: Homestead Final Certificates, by land office (cancelled entries: Canceled "
        "Homestead Files)",
    ),
    (
        "military_warrant",
        ("warrant", "scripwarrant", "bounty"),
        "Military bounty-land warrant. The patentee may be an assignee who bought the "
        "warrant; the warrantee (the veteran, his widow or heirs) is in the warrant "
        "application file, with service details.",
        "RG 15: Bounty Land Warrant Application Files (the veteran's application); RG 49: "
        "the surrendered warrant, filed by act and warrant number",
    ),
    (
        "preemption",
        ("preemption", "pre-emption"),
        "Preemption cash entry: the settler's proof of residence and improvements before purchase.",
        "RG 49: Land Entry Case Files (cash entries), by land office",
    ),
    (
        "cash",
        ("cash", "sale-cash", "sale cash"),
        "Cash entry: the purchase receipt and certificate; thin, but it dates the purchase "
        "at the local land office.",
        "RG 49: Land Entry Case Files (cash entries), by land office",
    ),
    (
        "credit",
        ("credit",),
        "Credit entry (1800-1820): purchase on instalments, with the payment record.",
        "RG 49: Land Entry Case Files (credit entries), by land office",
    ),
    (
        "timber_culture",
        ("timber culture", "timber-culture"),
        "Timber culture entry (1873-1891): proof of trees planted and kept, with witnesses.",
        "RG 49: Timber Culture Final Certificates, by land office",
    ),
    (
        "desert_land",
        ("desert",),
        "Desert land entry (from 1877): proof of irrigation.",
        "RG 49: Desert Land Entry Files, by land office",
    ),
    (
        "scrip",
        ("scrip",),
        "Scrip location (agricultural college, Indian, Valentine, Chippewa and other scrip).",
        "RG 49: scrip files, by kind of scrip",
    ),
    (
        "indian_allotment",
        ("allotment", "allotted", "indian allot"),
        "Indian allotment: allotment records name the allottee and often family members.",
        "RG 75 (Bureau of Indian Affairs) allotment records, and RG 49",
    ),
    (
        "private_claim",
        ("private land claim", "private claim", "donation"),
        "Private land claim or donation claim confirmed by Congress or a commission; the "
        "claim papers can reach back to Spanish, French or Mexican grants.",
        "RG 49: Private Land Claim files; Oregon and Washington donation land claims",
    ),
    (
        "state_grant",
        ("swamp", "state selection", "state grant", "school"),
        "A grant to a state (swamp land, school sections, state selections). The federal "
        "patent went to the state; the individual's title came from the state, so look in "
        "the state land office's records.",
        "None at NARA for the individual; the state's land office or archives",
    ),
)

#: The flat fee NARA charged to copy a land entry file, when last checked.
NATF_84_NOTE = (
    "Not digitised? Order it from NARA with NATF Form 84 (Order Online at archives.gov), "
    "quoting the land office, the kind of entry and the final certificate or entry number. "
    "NARA charged a flat $50 per file when this server's notes were last checked "
    "(October 2026)."
)

_YEAR = re.compile(r"\b(1[6-9]\d\d|20\d\d)\b")


def classify(authority: str) -> tuple[str, str, str]:
    """(kind, what the file is, series family) for a patent's Authority text."""
    text = authority.lower()
    for kind, words, what, series in ENTRY_TYPES:
        if any(w in text for w in words):
            return kind, what, series
    return (
        "unclassified",
        "The authority did not name a kind of entry this server knows; read it on the patent.",
        "RG 49, by land office: search the series for that office",
    )


def nara_search(
    kind: str, state: str | None, land_office: str, certificate: str, patentee: str
) -> list[dict]:
    """Argument sets for nara-catalog-mcp's ``search_records_advanced``, most specific first.

    The file-level title pattern is verified for digitised Nebraska homestead
    files ("Lincoln Land Office (Nebraska), Homestead Final Certificate No.
    12018" finds NAID 63668992). Elsewhere files are described only at
    series level, so the second set finds the series to order from.
    """
    state_name = STATE_NAMES.get(state or "", "")
    office = land_office.strip()
    office = re.sub(r"\s+land\s+office$", "", office, flags=re.IGNORECASE)
    out: list[dict] = []
    if kind == "homestead" and office and certificate and state_name:
        out.append(
            {
                "record_group_number": "49",
                "title": f"{office} Land Office ({state_name}), Homestead Final Certificate "
                f"No. {certificate}",
            }
        )
    if kind == "military_warrant" and patentee.strip():
        out.append(
            {"record_group_number": "15", "title": f"{patentee.strip()} bounty land warrant"}
        )
    series_words = {
        "homestead": "Homestead Final Certificates",
        "cash": "Land Entry Case Files",
        "preemption": "Land Entry Case Files",
        "credit": "Land Entry Case Files",
        "timber_culture": "Timber Culture",
        "desert_land": "Desert Land",
    }.get(kind)
    if series_words:
        search = {
            "record_group_number": "49",
            "title": series_words,
            "level_of_description": "series",
        }
        if office:
            search["query"] = office
        out.append(search)
    return out


def years(text: str) -> list[int]:
    return [int(y) for y in _YEAR.findall(text or "")]
