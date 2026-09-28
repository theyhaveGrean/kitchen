from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .models import Recipe
from .normalize import clean_text

ROUNDUP_TITLE_RE = re.compile(
    r"\b(?:\d{1,3}\+?\s+)?(?:best\s+|easy\s+|favorite\s+|top\s+)?"
    r".+?\b(?:recipes|recipe ideas|dinner ideas|meal ideas)\b",
    re.I,
)


def page_heading(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1")
    if h1:
        text = clean_text(h1.get_text(" ", strip=True))
        if text:
            return text
    if soup.title:
        return clean_text(soup.title.get_text(" ", strip=True))
    return ""


def looks_like_recipe_roundup(
    soup: BeautifulSoup, candidates: list[Recipe], source_url: str | None
) -> bool:
    """Reject editorial collections that embed multiple complete recipes."""
    url = (source_url or "").casefold()
    path = urlparse(url).path if url else ""
    heading = page_heading(soup)
    structured = [
        recipe for recipe in candidates
        if recipe.extraction_method in {"json-ld", "microdata", "rdfa", "itemprop-dom"}
        and len(recipe.ingredients) >= 2
        and len(recipe.instructions) >= 2
    ]
    distinct_titles = {clean_text(r.title).casefold() for r in structured if r.title}
    collection_path = bool(
        re.search(r"/(?:recipes?/)?(?:photos?|galleries?|gallery)/", path)
        or "/recipes-menus/" in path
        or re.search(r"/g\d+(?:/|$)", path)
    )
    if collection_path and (ROUNDUP_TITLE_RE.search(heading) or len(distinct_titles) >= 2):
        return True
    numbered_collection_heading = bool(
        re.search(r"\b\d{1,3}\+?\b", heading) and ROUNDUP_TITLE_RE.search(heading)
    )
    return numbered_collection_heading and len(distinct_titles) >= 2
