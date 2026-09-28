#!/usr/bin/env python3
"""
recipe_extractor.py

Best-effort recipe extractor for arbitrary public webpages.

Extraction order:
1. schema.org Recipe JSON-LD
2. Microdata / RDFa (if `extruct` is installed)
3. itemprop-based DOM markup
4. Heuristic recipe-card extraction from visible HTML
5. Optional Playwright-rendered retry for JavaScript-heavy pages

Usage:
    python recipe_extractor.py "https://example.com/recipe"
    python recipe_extractor.py "https://example.com/recipe" -o recipe.json
    python recipe_extractor.py "https://example.com/recipe" --render-js
    python recipe_extractor.py page.html --html-file

Recommended install:
    pip install requests beautifulsoup4 lxml extruct w3lib

Optional JS-rendering fallback:
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

# Recipe text frequently contains Unicode fractions (⅓, ½), degree signs, curly
# quotes, etc. Windows PowerShell may otherwise give stdout/stderr a legacy
# code page such as cp1252, which can crash JSON output before the parent
# process ever receives it.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

import requests
from bs4 import BeautifulSoup, Tag

try:
    import extruct  # type: ignore
    from w3lib.html import get_base_url  # type: ignore
except Exception:
    extruct = None
    get_base_url = None


DEFAULT_TIMEOUT = 20
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/154.0.0.0 Safari/537.36"
)

INGREDIENT_HEADINGS = (
    "ingredients", "ingredient", "what you'll need", "what you’ll need",
    "you will need", "for the recipe", "shopping list"
)
INSTRUCTION_HEADINGS = (
    "instructions", "directions", "method", "steps", "preparation",
    "preparation instructions", "how to make", "how to prepare"
)
STOP_HEADINGS = (
    "notes", "nutrition", "nutrition facts", "faq", "frequently asked questions",
    "storage", "variations", "substitutions", "tips", "comments", "reviews",
    "related recipes", "you may also like", "equipment"
)

STEP_VERBS = re.compile(
    r"\b(add|bake|beat|blend|boil|broil|chill|combine|cook|cool|cut|fold|"
    r"heat|knead|mix|pour|preheat|reduce|remove|roast|season|serve|simmer|"
    r"stir|whisk|saute|sauté|sear|sprinkle|transfer|refrigerate|freeze|"
    r"place|set|let|melt|drain|slice|chop)\b",
    re.I,
)

QUANTITY_RE = re.compile(
    r"^\s*(?:\d+(?:[./]\d+)?|\d+\s+\d+/\d+|[¼½¾⅓⅔⅛⅜⅝⅞]|one|two|three|four|"
    r"five|six|seven|eight|nine|ten)\b",
    re.I,
)

DURATION_KEYS = {"prepTime", "cookTime", "totalTime", "performTime"}


@dataclass
class Recipe:
    source_url: str | None = None
    title: str | None = None
    description: str | None = None
    author: str | None = None
    recipe_yield: str | None = None
    prep_time: str | None = None
    cook_time: str | None = None
    total_time: str | None = None
    cuisine: list[str] = field(default_factory=list)
    category: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    ingredient_sections: list[dict[str, Any]] = field(default_factory=list)
    instruction_sections: list[dict[str, Any]] = field(default_factory=list)
    ingredients: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)
    nutrition: dict[str, Any] | None = None
    extraction_method: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return str(value)
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def unique_nonempty(values: Iterable[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = clean_text(v)
        key = s.casefold()
        if s and key not in seen:
            seen.add(key)
            out.append(s)
    return out


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return clean_text(value) or None
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        vals = [scalar_text(v) for v in value]
        vals = [v for v in vals if v]
        return ", ".join(vals) if vals else None
    if isinstance(value, dict):
        for key in ("name", "text", "value", "@value"):
            if key in value:
                return scalar_text(value[key])
    return clean_text(value) or None


def list_text(value: Any) -> list[str]:
    if value is None:
        return []
    vals = as_list(value)
    out: list[str] = []
    for v in vals:
        if isinstance(v, dict):
            text = scalar_text(v)
            if text:
                out.append(text)
        else:
            text = scalar_text(v)
            if text:
                out.append(text)
    return unique_nonempty(out)


def iso8601_duration_to_human(value: str | None) -> str | None:
    """Convert common ISO-8601 durations like PT1H30M to '1 hr 30 min'."""
    if not value:
        return None
    s = value.strip()
    m = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?"
        r"(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?",
        s,
        re.I,
    )
    if not m:
        return clean_text(s)
    parts = []
    d = int(m.group("days") or 0)
    h = int(m.group("hours") or 0)
    mins = int(m.group("minutes") or 0)
    sec = int(m.group("seconds") or 0)
    if d:
        parts.append(f"{d} day" + ("s" if d != 1 else ""))
    if h:
        parts.append(f"{h} hr")
    if mins:
        parts.append(f"{mins} min")
    if sec:
        parts.append(f"{sec} sec")
    return " ".join(parts) if parts else clean_text(s)


def type_contains(obj: dict[str, Any], wanted: str) -> bool:
    t = obj.get("@type") or obj.get("type")
    types = as_list(t)
    return any(str(x).split("/")[-1].casefold() == wanted.casefold() for x in types)


def walk_json(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_json(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from walk_json(item)


def parse_json_lenient(text: str) -> Any:
    text = text.strip().lstrip("\ufeff")
    if not text:
        return None

    # Fast path: valid JSON.
    try:
        return json.loads(text)
    except Exception:
        pass

    # Common malformed pattern: multiple top-level JSON objects.
    decoder = json.JSONDecoder()
    objects = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        try:
            obj, j = decoder.raw_decode(text, i)
            objects.append(obj)
            i = j
        except Exception:
            break
    if objects:
        return objects

    # Some sites wrap JSON in HTML comments / CDATA.
    stripped = re.sub(r"^\s*(?:<!--|//<!\[CDATA\[)", "", text)
    stripped = re.sub(r"(?:-->|//\]\]>)\s*$", "", stripped)
    try:
        return json.loads(stripped)
    except Exception:
        return None


def instruction_tree(value: Any, current_section: str | None = None):
    """
    Yield (section_name, step_text) while preserving HowToSection grouping.
    """
    if value is None:
        return

    if isinstance(value, str):
        txt = clean_text(value)
        if not txt:
            return
        # Some JSON-LD stores all directions in one block.
        chunks = split_instruction_blob(txt)
        for chunk in chunks:
            yield current_section, chunk
        return

    if isinstance(value, list):
        for item in value:
            yield from instruction_tree(item, current_section)
        return

    if not isinstance(value, dict):
        txt = clean_text(value)
        if txt:
            yield current_section, txt
        return

    if type_contains(value, "HowToSection"):
        section = scalar_text(value.get("name")) or current_section
        items = value.get("itemListElement") or value.get("steps") or value.get("recipeInstructions")
        if items is not None:
            yield from instruction_tree(items, section)
        return

    if type_contains(value, "HowToStep"):
        txt = scalar_text(value.get("text")) or scalar_text(value.get("name"))
        if txt:
            yield current_section, txt
        return

    if "itemListElement" in value:
        yield from instruction_tree(value["itemListElement"], current_section)
        return

    txt = scalar_text(value.get("text")) or scalar_text(value.get("name"))
    if txt:
        yield current_section, txt


def split_instruction_blob(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []

    # Split explicit numbered steps.
    numbered = re.split(r"\s+(?=\d{1,2}[.)]\s+)", text)
    if len(numbered) > 1:
        return [re.sub(r"^\d{1,2}[.)]\s*", "", x).strip() for x in numbered if x.strip()]

    # Split sentence blocks only if they look like separate imperative steps.
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    if len(sentences) >= 2 and sum(bool(STEP_VERBS.search(x)) for x in sentences) >= 2:
        return [x.strip() for x in sentences if len(x.strip()) > 3]

    return [text]


def image_urls(value: Any, base_url: str | None) -> list[str]:
    candidates: list[str] = []
    for item in as_list(value):
        if isinstance(item, str):
            candidates.append(item)
        elif isinstance(item, dict):
            for key in ("url", "contentUrl", "thumbnailUrl"):
                if item.get(key):
                    candidates.append(str(item[key]))
                    break
    out = []
    for u in candidates:
        u = clean_text(u)
        if not u:
            continue
        out.append(urljoin(base_url, u) if base_url else u)
    return unique_nonempty(out)


def normalize_recipe_dict(data: dict[str, Any], source_url: str | None, method: str) -> Recipe:
    recipe = Recipe(source_url=source_url)
    recipe.title = scalar_text(data.get("name") or data.get("headline"))
    recipe.description = scalar_text(data.get("description"))
    recipe.author = scalar_text(data.get("author"))
    recipe.recipe_yield = scalar_text(data.get("recipeYield") or data.get("yield"))

    recipe.prep_time = iso8601_duration_to_human(scalar_text(data.get("prepTime")))
    recipe.cook_time = iso8601_duration_to_human(scalar_text(data.get("cookTime")))
    recipe.total_time = iso8601_duration_to_human(scalar_text(data.get("totalTime")))

    recipe.cuisine = list_text(data.get("recipeCuisine"))
    recipe.category = list_text(data.get("recipeCategory"))
    recipe.keywords = list_text(data.get("keywords"))
    recipe.images = image_urls(data.get("image"), source_url)

    raw_ingredients = (
        data.get("recipeIngredient")
        or data.get("ingredients")
        or data.get("supply")
    )
    recipe.ingredients = list_text(raw_ingredients)
    if recipe.ingredients:
        recipe.ingredient_sections = [{"name": None, "items": recipe.ingredients.copy()}]

    grouped: dict[str | None, list[str]] = {}
    for section, step in instruction_tree(data.get("recipeInstructions") or data.get("instructions")):
        step = clean_text(step)
        if step:
            grouped.setdefault(section, []).append(step)

    for section, steps in grouped.items():
        recipe.instruction_sections.append({"name": section, "steps": unique_nonempty(steps)})
    recipe.instructions = [
        step
        for section in recipe.instruction_sections
        for step in section["steps"]
    ]

    nutrition = data.get("nutrition")
    recipe.nutrition = nutrition if isinstance(nutrition, dict) else None

    recipe.extraction_method = method
    recipe.confidence = score_recipe(recipe)
    return recipe


def score_recipe(r: Recipe) -> float:
    score = 0.0
    if r.title:
        score += 0.10
    if len(r.ingredients) >= 2:
        score += 0.35
    elif r.ingredients:
        score += 0.15
    if len(r.instructions) >= 2:
        score += 0.35
    elif r.instructions:
        score += 0.15
    if r.recipe_yield:
        score += 0.05
    if r.prep_time or r.cook_time or r.total_time:
        score += 0.05
    if r.images:
        score += 0.05
    if r.author:
        score += 0.05
    return round(min(score, 1.0), 2)


def extract_jsonld(soup: BeautifulSoup, source_url: str | None) -> list[Recipe]:
    candidates: list[Recipe] = []
    for script in soup.find_all("script"):
        script_type = (script.get("type") or "").lower()
        if "ld+json" not in script_type:
            continue
        raw = script.string if script.string is not None else script.get_text()
        parsed = parse_json_lenient(raw or "")
        if parsed is None:
            continue

        for obj in walk_json(parsed):
            if type_contains(obj, "Recipe"):
                candidates.append(normalize_recipe_dict(obj, source_url, "json-ld"))

    return candidates


def extract_extruct(html_text: str, source_url: str | None) -> list[Recipe]:
    if extruct is None:
        return []
    try:
        base = get_base_url(html_text, source_url or "") if get_base_url else (source_url or "")
        data = extruct.extract(
            html_text,
            base_url=base,
            syntaxes=["microdata", "rdfa", "json-ld"],
            uniform=True,
        )
    except Exception:
        return []

    candidates: list[Recipe] = []
    for syntax in ("microdata", "rdfa"):
        for obj in data.get(syntax, []) or []:
            for node in walk_json(obj):
                if type_contains(node, "Recipe"):
                    candidates.append(normalize_recipe_dict(node, source_url, syntax))
    return candidates


def prop_value(node: Tag) -> str:
    for attr in ("content", "datetime", "value", "href", "src"):
        if node.has_attr(attr):
            return clean_text(node.get(attr))
    return clean_text(node.get_text(" ", strip=True))


def extract_itemprops(soup: BeautifulSoup, source_url: str | None) -> list[Recipe]:
    roots = []
    for tag in soup.find_all(attrs={"itemtype": True}):
        itemtype = " ".join(as_list(tag.get("itemtype")))
        if "schema.org/Recipe" in itemtype or itemtype.rstrip("/").endswith("/Recipe"):
            roots.append(tag)

    if not roots:
        # Some pages use itemprop fields without a Recipe root.
        if soup.find(attrs={"itemprop": re.compile(r"recipeIngredient|ingredients", re.I)}):
            roots = [soup]

    out: list[Recipe] = []
    for root in roots[:10]:
        def first_prop(*names: str) -> str | None:
            for name in names:
                node = root.find(attrs={"itemprop": name})
                if node:
                    v = prop_value(node)
                    if v:
                        return v
            return None

        ingredient_nodes = root.find_all(
            attrs={"itemprop": re.compile(r"^(recipeIngredient|ingredients)$", re.I)}
        )
        ingredients = unique_nonempty(prop_value(x) for x in ingredient_nodes)

        instruction_nodes = root.find_all(
            attrs={"itemprop": re.compile(r"^(recipeInstructions|instructions)$", re.I)}
        )
        steps: list[str] = []
        for n in instruction_nodes:
            if n.find_all(["li", "p"]):
                steps.extend(clean_text(x.get_text(" ", strip=True)) for x in n.find_all(["li", "p"]))
            else:
                steps.extend(split_instruction_blob(prop_value(n)))
        steps = unique_nonempty(steps)

        r = Recipe(
            source_url=source_url,
            title=first_prop("name", "headline"),
            description=first_prop("description"),
            author=first_prop("author"),
            recipe_yield=first_prop("recipeYield"),
            prep_time=iso8601_duration_to_human(first_prop("prepTime")),
            cook_time=iso8601_duration_to_human(first_prop("cookTime")),
            total_time=iso8601_duration_to_human(first_prop("totalTime")),
            ingredients=ingredients,
            instructions=steps,
            ingredient_sections=[{"name": None, "items": ingredients}] if ingredients else [],
            instruction_sections=[{"name": None, "steps": steps}] if steps else [],
            extraction_method="itemprop-dom",
        )
        r.confidence = score_recipe(r)
        out.append(r)
    return out


def visible_text(tag: Tag) -> str:
    return clean_text(tag.get_text(" ", strip=True))


def heading_level(tag: Tag) -> int:
    if tag.name and re.fullmatch(r"h[1-6]", tag.name.lower()):
        return int(tag.name[1])
    return 7


def heading_matches(text: str, options: tuple[str, ...]) -> bool:
    t = re.sub(r"[^a-z0-9'’ ]+", " ", text.casefold())
    t = re.sub(r"\s+", " ", t).strip()
    return any(t == x or t.startswith(x + " ") for x in options)


def find_heading(soup: BeautifulSoup, options: tuple[str, ...]) -> Tag | None:
    candidates: list[tuple[int, int, Tag]] = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"]):
        txt = visible_text(tag)
        if 1 <= len(txt) <= 80 and heading_matches(txt, options):
            # Prefer actual headings and shorter text.
            candidates.append((heading_level(tag), len(txt), tag))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][2]


def collect_after_heading(heading: Tag, mode: str) -> list[Tag]:
    """
    Collect likely list/paragraph nodes after a heading until the next major heading.
    """
    level = heading_level(heading)
    items: list[Tag] = []

    for node in heading.find_all_next():
        if node is heading:
            continue

        if node.name and re.fullmatch(r"h[1-6]", node.name.lower()):
            node_level = heading_level(node)
            txt = visible_text(node)
            if node_level <= level or heading_matches(
                txt, INSTRUCTION_HEADINGS + INGREDIENT_HEADINGS + STOP_HEADINGS
            ):
                break

        if mode == "ingredients":
            if node.name == "li":
                items.append(node)
            elif node.name == "p":
                txt = visible_text(node)
                if QUANTITY_RE.search(txt) and len(txt) < 240:
                    items.append(node)
        else:
            if node.name == "li":
                items.append(node)
            elif node.name == "p":
                txt = visible_text(node)
                if len(txt) >= 20 and STEP_VERBS.search(txt):
                    items.append(node)

        if len(items) >= 100:
            break

    # De-duplicate nested nodes by text.
    seen = set()
    deduped = []
    for item in items:
        txt = visible_text(item)
        key = txt.casefold()
        if txt and key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def find_recipe_container(soup: BeautifulSoup) -> Tag | None:
    patterns = re.compile(
        r"(recipe[-_ ]?(card|container|content|block|instructions?|ingredients?)|"
        r"wprm-recipe|tasty-recipes|mv-create|easyrecipe|zip-recipes|"
        r"recipe-callout|recipe__)",
        re.I,
    )
    candidates: list[tuple[int, Tag]] = []
    for tag in soup.find_all(["article", "section", "div", "main"]):
        marker = " ".join([
            tag.get("id") or "",
            " ".join(tag.get("class") or []),
        ])
        if patterns.search(marker):
            txt = visible_text(tag)
            if 200 <= len(txt) <= 50000:
                # Prefer containers containing both ingredient/instruction language.
                bonus = 0
                low = txt.casefold()
                if "ingredient" in low:
                    bonus += 2000
                if "instruction" in low or "direction" in low or "method" in low:
                    bonus += 2000
                candidates.append((bonus - len(txt), tag))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def heuristic_sections_from_container(container: Tag) -> tuple[list[str], list[str]]:
    ingredients: list[str] = []
    instructions: list[str] = []

    # Common class/id patterns.
    ing_re = re.compile(r"(ingredient|recipe-ingredients)", re.I)
    inst_re = re.compile(r"(instruction|direction|method|recipe-steps?)", re.I)

    ing_nodes = container.find_all(
        lambda t: isinstance(t, Tag)
        and (
            ing_re.search(t.get("id") or "")
            or ing_re.search(" ".join(t.get("class") or []))
        )
    )
    for area in ing_nodes[:10]:
        for node in area.find_all(["li", "p"]):
            txt = visible_text(node)
            if 2 < len(txt) < 300:
                ingredients.append(txt)

    inst_nodes = container.find_all(
        lambda t: isinstance(t, Tag)
        and (
            inst_re.search(t.get("id") or "")
            or inst_re.search(" ".join(t.get("class") or []))
        )
    )
    for area in inst_nodes[:10]:
        for node in area.find_all(["li", "p"]):
            txt = visible_text(node)
            if 10 < len(txt) < 1200:
                instructions.append(txt)

    return unique_nonempty(ingredients), unique_nonempty(instructions)


def extract_heuristic(soup: BeautifulSoup, source_url: str | None) -> Recipe | None:
    # Remove obvious noise before text heuristics.
    clone = BeautifulSoup(str(soup), "lxml")
    for tag in clone(["script", "style", "noscript", "svg", "nav", "footer", "form", "aside"]):
        tag.decompose()

    container = find_recipe_container(clone) or clone
    ingredients, instructions = heuristic_sections_from_container(container)

    if len(ingredients) < 2:
        h = find_heading(container, INGREDIENT_HEADINGS)
        if h:
            ingredients = unique_nonempty(visible_text(x) for x in collect_after_heading(h, "ingredients"))

    if len(instructions) < 2:
        h = find_heading(container, INSTRUCTION_HEADINGS)
        if h:
            instructions = unique_nonempty(visible_text(x) for x in collect_after_heading(h, "instructions"))

    # Basic sanity filters.
    ingredients = [
        x for x in ingredients
        if 2 < len(x) < 300
        and not heading_matches(x, INSTRUCTION_HEADINGS + STOP_HEADINGS)
    ]
    instructions = [
        x for x in instructions
        if 10 < len(x) < 1500
        and not heading_matches(x, INGREDIENT_HEADINGS + STOP_HEADINGS)
    ]

    if not ingredients and not instructions:
        return None

    title = None
    h1 = clone.find("h1")
    if h1:
        title = visible_text(h1)
    if not title and clone.title:
        title = clean_text(clone.title.get_text(" ", strip=True))

    r = Recipe(
        source_url=source_url,
        title=title,
        ingredients=unique_nonempty(ingredients),
        instructions=unique_nonempty(instructions),
        extraction_method="html-heuristic",
    )
    if r.ingredients:
        r.ingredient_sections = [{"name": None, "items": r.ingredients.copy()}]
    if r.instructions:
        r.instruction_sections = [{"name": None, "steps": r.instructions.copy()}]
    r.confidence = score_recipe(r)
    r.warnings.append(
        "Recipe was inferred from page structure because no reliable structured recipe metadata was found."
    )
    return r


def choose_best(candidates: list[Recipe]) -> Recipe | None:
    if not candidates:
        return None

    method_priority = {
        "json-ld": 4,
        "microdata": 3,
        "rdfa": 3,
        "itemprop-dom": 2,
        "html-heuristic": 1,
    }

    def key(r: Recipe):
        return (
            r.confidence,
            method_priority.get(r.extraction_method or "", 0),
            len(r.ingredients) + len(r.instructions),
        )

    return max(candidates, key=key)


def fetch_static(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }

    with requests.Session() as session:
        resp = session.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()

        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" not in ctype and "xhtml" not in ctype and ctype:
            raise ValueError(f"URL did not return HTML (Content-Type: {ctype})")

        resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
        return resp.text, resp.url


def fetch_with_playwright(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """
    Render a page in Chromium.

    This is deliberately the fallback rather than the primary fetch path:
    structured recipe JSON-LD usually does not require a browser, while some
    publishers reject non-browser HTTP clients with 403/429/503 responses.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Playwright is required for browser fallback. Install it with: "
            "pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = browser.new_context(
            user_agent=DEFAULT_UA,
            locale="en-US",
            viewport={"width": 1440, "height": 1000},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Upgrade-Insecure-Requests": "1",
            },
        )
        page = context.new_page()

        response = page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout * 1000,
        )

        # Give client-rendered recipe cards/JSON-LD a chance to appear.
        try:
            page.wait_for_load_state(
                "networkidle",
                timeout=min(timeout, 8) * 1000,
            )
        except Exception:
            pass

        # We do not reject a browser response solely because of its status:
        # some anti-bot/interstitial setups still produce usable DOM content.
        html_text = page.content()
        final_url = page.url

        context.close()
        browser.close()

    if not html_text or len(html_text) < 100:
        status = response.status if response is not None else "unknown"
        raise RuntimeError(f"Browser returned no usable HTML (HTTP status {status}).")

    return html_text, final_url


def extract_from_html(html_text: str, source_url: str | None) -> Recipe | None:
    soup = BeautifulSoup(html_text, "lxml")
    candidates: list[Recipe] = []

    candidates.extend(extract_jsonld(soup, source_url))
    candidates.extend(extract_extruct(html_text, source_url))
    candidates.extend(extract_itemprops(soup, source_url))

    heuristic = extract_heuristic(soup, source_url)
    if heuristic:
        candidates.append(heuristic)

    return choose_best(candidates)


def looks_weak(recipe: Recipe | None) -> bool:
    if recipe is None:
        return True
    return recipe.confidence < 0.65 or len(recipe.ingredients) < 2 or len(recipe.instructions) < 2


def extract_recipe(
    url: str,
    *,
    render_js: bool = False,
    auto_render_js: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> Recipe:
    """
    Fetch and extract one recipe.

    Normal path:
        requests -> structured/DOM extraction

    Browser fallback path:
        - user explicitly passes --render-js
        - static extraction is weak
        - publisher rejects requests with a likely anti-bot/transient status
          such as 401, 403, 429, 503

    A genuine 404/410 is *not* hidden by the browser fallback.
    """
    recipe: Recipe | None = None
    final_url = url
    static_error: Exception | None = None
    blocked_status: int | None = None

    # If --render-js is explicitly requested, try the browser first.
    if render_js:
        try:
            rendered_html, rendered_url = fetch_with_playwright(url, timeout=timeout)
            recipe = extract_from_html(rendered_html, rendered_url)
            final_url = rendered_url
            if recipe:
                recipe.warnings.append("JavaScript/browser rendering was used.")
        except Exception as exc:
            static_error = exc

    # Fast/static path unless browser-first already succeeded.
    if recipe is None and not render_js:
        try:
            html_text, final_url = fetch_static(url, timeout=timeout)
            recipe = extract_from_html(html_text, final_url)
        except requests.HTTPError as exc:
            static_error = exc
            if exc.response is not None:
                blocked_status = exc.response.status_code

            # 404/410 normally means the test URL itself is stale, not that the
            # site merely dislikes our HTTP client.
            if blocked_status in {404, 410}:
                raise

            # Common anti-bot/rate-limit/service statuses. Let browser fallback
            # below try the same public page as a normal browser would.
            if blocked_status not in {401, 403, 429, 503}:
                raise
        except requests.RequestException as exc:
            static_error = exc
            # Network-level failures may still succeed in a browser; let the
            # fallback below try if enabled.

    should_retry_js = (
        auto_render_js
        and (
            recipe is None
            or looks_weak(recipe)
            or blocked_status in {401, 403, 429, 503}
        )
    )

    if should_retry_js and not (render_js and recipe is not None):
        try:
            rendered_html, rendered_url = fetch_with_playwright(url, timeout=timeout)
            rendered_recipe = extract_from_html(rendered_html, rendered_url)

            if rendered_recipe and (
                recipe is None
                or rendered_recipe.confidence > recipe.confidence
                or (
                    rendered_recipe.confidence == recipe.confidence
                    and len(rendered_recipe.ingredients) + len(rendered_recipe.instructions)
                    > len(recipe.ingredients) + len(recipe.instructions)
                )
            ):
                recipe = rendered_recipe
                final_url = rendered_url
                if blocked_status:
                    recipe.warnings.append(
                        f"Static HTTP fetch returned {blocked_status}; browser fallback was used."
                    )
                else:
                    recipe.warnings.append("JavaScript/browser rendering was used.")
        except Exception as browser_exc:
            if recipe is not None:
                recipe.warnings.append(
                    f"Browser fallback unavailable or failed: {browser_exc}"
                )
            else:
                static_msg = f" Static fetch error: {static_error}" if static_error else ""
                raise RuntimeError(
                    f"Static extraction failed and browser fallback also failed. "
                    f"Browser error: {browser_exc}.{static_msg}"
                ) from browser_exc

    if recipe is None:
        if static_error is not None:
            raise RuntimeError(f"Recipe extraction failed: {static_error}")
        raise ValueError("No recipe-like content could be extracted from this page.")

    recipe.source_url = final_url
    recipe.confidence = score_recipe(recipe)

    if not recipe.ingredients:
        recipe.warnings.append("No ingredient list was found.")
    if not recipe.instructions:
        recipe.warnings.append("No instruction list was found.")
    if recipe.confidence < 0.65:
        recipe.warnings.append("Low-confidence extraction; review the output before using it.")

    return recipe


def load_html_file(path: str) -> tuple[str, str]:
    p = Path(path).expanduser().resolve()
    return p.read_text(encoding="utf-8", errors="replace"), p.as_uri()


def recipe_to_dict(recipe: Recipe) -> dict[str, Any]:
    """
    Output a stable JSON shape. None/empty optional values are retained so your
    application can rely on consistent keys.
    """
    return asdict(recipe)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a recipe from a webpage into normalized JSON."
    )
    parser.add_argument("source", help="Recipe URL, or HTML file with --html-file")
    parser.add_argument("-o", "--output", help="Write JSON to this file")
    parser.add_argument(
        "--render-js",
        action="store_true",
        help="Force Playwright browser rendering before/after static extraction",
    )
    parser.add_argument(
        "--no-auto-render-js",
        action="store_true",
        help="Do not automatically try Playwright when static extraction looks weak",
    )
    parser.add_argument(
        "--html-file",
        action="store_true",
        help="Treat SOURCE as a local HTML file rather than a URL",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON rather than pretty-printed JSON",
    )
    args = parser.parse_args()

    try:
        if args.html_file:
            html_text, source_url = load_html_file(args.source)
            recipe = extract_from_html(html_text, source_url)
            if recipe is None:
                raise ValueError("No recipe-like content could be extracted from the HTML file.")
        else:
            if not re.match(r"^https?://", args.source, re.I):
                raise ValueError("SOURCE must be an http(s) URL unless --html-file is used.")
            recipe = extract_recipe(
                args.source,
                render_js=args.render_js,
                auto_render_js=not args.no_auto_render_js,
                timeout=args.timeout,
            )

        payload = recipe_to_dict(recipe)
        text = json.dumps(
            payload,
            ensure_ascii=False,
            indent=None if args.compact else 2,
        )

        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
            print(f"Wrote {args.output}", file=sys.stderr)
        else:
            print(text)
        return 0

    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        print(f"HTTP error {status}: {exc}", file=sys.stderr)
        return 2
    except requests.RequestException as exc:
        print(f"Network error: {exc}", file=sys.stderr)
        return 3
    except Exception as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
