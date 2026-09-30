"""Core recipe extraction pipeline.

Parser fallbacks intentionally live together here because their ordering and scoring
are tightly coupled. Network fetching, output normalization, models, and page-level
validation are separated into focused modules.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from .fetch.web import fetch_with_scrapling
from .models import Recipe
from .normalize import recipe_to_dict
from .validation import looks_like_recipe_roundup

# Recipe text frequently contains Unicode fractions (⅓, ½), degree signs, curly
# quotes, etc. Windows PowerShell may otherwise give stdout/stderr a legacy
# code page such as cp1252, which can crash JSON output before the parent
# process ever receives it.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from bs4 import BeautifulSoup, Tag

try:
    from scrapling.parser import Selector as ScraplingSelector  # type: ignore
except Exception:
    ScraplingSelector = None

try:
    import extruct  # type: ignore
    from w3lib.html import get_base_url  # type: ignore
except Exception:
    extruct = None
    get_base_url = None


DEFAULT_TIMEOUT = 60
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
    return " ".join(parts) if parts else None


def normalize_recipe_yield(value: Any) -> str | None:
    """Prefer the human-readable recipeYield when publishers provide both a count and label."""
    values = list_text(value)
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    # Common schema.org pattern: ["10", "10-12 rolls"]. Avoid "10, 10-12 rolls".
    descriptive = [
        v for v in values
        if not re.fullmatch(r"\s*\d+(?:\.\d+)?\s*", v)
    ]
    if descriptive:
        # Prefer a value that contains units/words; preserve source ordering on ties.
        return max(descriptive, key=lambda v: (bool(re.search(r"[A-Za-z]", v)), len(v)))
    return values[0]


KNOWN_CUISINES = {
    "american", "british", "chinese", "french", "greek", "indian", "irish",
    "italian", "japanese", "korean", "mediterranean", "mexican", "middle eastern",
    "moroccan", "spanish", "thai", "turkish", "vietnamese", "southern", "cajun",
    "creole", "caribbean", "german", "filipino", "indonesian", "persian", "lebanese",
    "brazilian", "argentinian", "australian", "canadian", "hawaiian",
}


def normalize_cuisine(value: Any) -> list[str]:
    values = list_text(value)
    cleaned: list[str] = []
    for item in values:
        text = clean_text(item)
        m = re.fullmatch(r"(.+?)\s+cuisine", text, re.I)
        if m:
            base = clean_text(m.group(1))
            # Hearst pages sometimes emit ingredient/topic tags such as
            # "Pancake Cuisine" and "Sour Cream Cuisine". Keep only real cuisine labels.
            if base.casefold() not in KNOWN_CUISINES:
                continue
            text = base
        cleaned.append(text)
    return unique_nonempty(cleaned)


KEYWORD_JUNK_RE = re.compile(
    r"^(?:content[-_ ]?type|locale|display\s*type|content\s*id|subsection|"
    r"collection|sponsored|is\s*syndicated|category|occasion|total\s*time|"
    r"filter\s*time|nutrition)\s*:",
    re.I,
)


def normalize_keywords(value: Any) -> list[str]:
    raw: list[str] = []
    for item in as_list(value):
        text = scalar_text(item)
        if not text:
            continue
        # schema.org keywords are frequently one comma-delimited string.
        raw.extend(x.strip() for x in re.split(r"[,;\n|]+", text) if x.strip())
    return unique_nonempty(x for x in raw if not KEYWORD_JUNK_RE.search(x))


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
    recipe.recipe_yield = normalize_recipe_yield(data.get("recipeYield") or data.get("yield"))

    recipe.prep_time = iso8601_duration_to_human(scalar_text(data.get("prepTime")))
    recipe.cook_time = iso8601_duration_to_human(scalar_text(data.get("cookTime")))
    recipe.total_time = iso8601_duration_to_human(scalar_text(data.get("totalTime")))

    recipe.cuisine = normalize_cuisine(data.get("recipeCuisine"))
    recipe.category = list_text(data.get("recipeCategory"))
    recipe.keywords = normalize_keywords(data.get("keywords"))
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
            recipe_yield=normalize_recipe_yield(first_prop("recipeYield")),
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


def scrapling_text(node: Any) -> str:
    try:
        return clean_text(node.get_all_text(strip=True))
    except Exception:
        try:
            return clean_text(node.text)
        except Exception:
            return clean_text(str(node))


def extract_scrapling_dom(html_text: str, source_url: str | None) -> Recipe | None:
    """Recipe-card fallback using Scrapling's DOM parser (no schema required)."""
    if ScraplingSelector is None:
        return None
    try:
        page = ScraplingSelector(content=html_text, url=source_url or "")
    except Exception:
        return None

    ingredient_selectors = [
        '[itemprop="recipeIngredient"]',
        '.wprm-recipe-ingredient',
        '.tasty-recipes-ingredients li',
        '.mv-create-ingredients li',
        '.zip-recipes-ingredients li',
        '[class*="ingredients"] li',
        '[class*="ingredient-list"] li',
        '[class*="ingredient-item"]',
        '[class*="ingredients__item"]',
    ]
    instruction_selectors = [
        '.wprm-recipe-instruction',
        '.tasty-recipes-instructions li',
        '.mv-create-instructions li',
        '.zip-recipes-instructions li',
        '[class*="instructions"] li',
        '[class*="directions"] li',
        '[class*="instruction-item"]',
        '[class*="recipe-step"]',
    ]

    def collect(selectors: list[str], min_len: int, max_len: int) -> list[str]:
        vals: list[str] = []
        for selector in selectors:
            try:
                for node in page.css(selector):
                    text = scrapling_text(node)
                    if min_len <= len(text) <= max_len:
                        vals.append(text)
            except Exception:
                continue
        return unique_nonempty(vals)

    ingredients = collect(ingredient_selectors, 2, 300)
    instructions = collect(instruction_selectors, 10, 1500)
    if len(ingredients) < 2 and len(instructions) < 2:
        return None

    title = None
    try:
        h1 = page.css("h1").first
        if h1:
            title = scrapling_text(h1)
    except Exception:
        pass

    r = Recipe(
        source_url=source_url,
        title=title,
        ingredients=ingredients,
        instructions=instructions,
        extraction_method="scrapling-dom",
    )
    if ingredients:
        r.ingredient_sections = [{"name": None, "items": ingredients.copy()}]
    if instructions:
        r.instruction_sections = [{"name": None, "steps": instructions.copy()}]
    r.confidence = score_recipe(r)
    r.warnings.append(
        "Recipe was extracted from recipe-card DOM patterns because structured Recipe metadata was unavailable or unusable."
    )
    return r


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
        "itemprop-dom": 3,
        "scrapling-dom": 2,
        "html-heuristic": 1,
    }

    def key(r: Recipe):
        return (
            r.confidence,
            method_priority.get(r.extraction_method or "", 0),
            len(r.ingredients) + len(r.instructions),
        )

    return max(candidates, key=key)



def extract_from_html(html_text: str, source_url: str | None) -> Recipe | None:
    soup = BeautifulSoup(html_text, "lxml")
    candidates: list[Recipe] = []

    candidates.extend(extract_jsonld(soup, source_url))
    candidates.extend(extract_extruct(html_text, source_url))
    candidates.extend(extract_itemprops(soup, source_url))

    scrapling_dom = extract_scrapling_dom(html_text, source_url)
    if scrapling_dom:
        candidates.append(scrapling_dom)

    heuristic = extract_heuristic(soup, source_url)
    if heuristic:
        candidates.append(heuristic)

    if looks_like_recipe_roundup(soup, candidates, source_url):
        return None

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
    """Fetch and extract one recipe using Scrapling for the entire network path.

    ``render_js`` and ``auto_render_js`` are retained as compatibility arguments
    for the existing batch runner, but Scrapling's StealthyFetcher is always used
    and always provides browser/JavaScript rendering.
    """
    html_text, final_url = fetch_with_scrapling(url, timeout=timeout)
    recipe = extract_from_html(html_text, final_url)

    if recipe is None:
        raise ValueError("No recipe-like content could be extracted from this page.")

    recipe.source_url = final_url
    recipe.confidence = score_recipe(recipe)
    recipe.warnings.append("Page fetched with Scrapling StealthyFetcher.")

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



def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a recipe from a webpage into normalized JSON."
    )
    parser.add_argument("source", help="Recipe URL, or HTML file with --html-file")
    parser.add_argument("-o", "--output", help="Write JSON to this file")
    parser.add_argument(
        "--render-js",
        action="store_true",
        help="Compatibility flag; Scrapling browser rendering is always used",
    )
    parser.add_argument(
        "--no-auto-render-js",
        action="store_true",
        help="Compatibility flag; Scrapling remains the only network fetcher",
    )
    parser.add_argument(
        "--html-file",
        action="store_true",
        help="Treat SOURCE as a local HTML file rather than a URL",
    )
    parser.add_argument(
        "--timeout", type=int, default=DEFAULT_TIMEOUT,
        help="Scrapling browser timeout in seconds; 0 disables it (default: 0)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON rather than pretty-printed JSON",
    )
    parser.add_argument(
        "--debug-metadata",
        action="store_true",
        help=argparse.SUPPRESS,
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

        payload = recipe_to_dict(recipe, include_debug=args.debug_metadata)
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

    except Exception as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
