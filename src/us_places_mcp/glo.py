"""Addresses on BLM's General Land Office Records site, for a person to open.

The site (glorecords.blm.gov, rebuilt in July 2026) has no public API, and
its pre-2026 deep links now redirect to the home page. Its search page
forwards a ``searchTerm`` parameter into its search frame as a path, so a
search can be linked as ``/s/advanced-search?searchTerm=<url-encoded
/search?q=...>``. That form was verified on 2026-10-04 for a free-text
search; the state and document-category filters follow the site's code and
are not verified.

A record link uses the document id the site shows. Whether those ids survive
re-indexing is unknown, so a citation should rest on the accession number,
document number, state and signature date, never on the link.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

SITE = "https://glorecords.blm.gov/s/advanced-search"

#: Document categories the site's facet offers.
CATEGORIES = ("Patent", "Survey", "Tractbook", "CDI", "LSR")


def search_link(text: str, state: str | None = None, category: str | None = None) -> str:
    """A link to a GLO search, 25 results a page."""
    params = [("q", " ".join(text.split())), ("page", "1"), ("pageSize", "25")]
    if state:
        params.append(("State", state))
    if category:
        params.append(("documenttype", category))
    inner = "/search?" + urlencode(params)
    return f"{SITE}?searchTerm={quote(inner, safe='')}"


def record_link(document_id: str, page_id: str | None = None) -> str:
    """A link to one record by the site's document id."""
    tail = f"&pageid={page_id}" if page_id else ""
    return f"{SITE}#/searchresults?documentid={document_id}{tail}"
