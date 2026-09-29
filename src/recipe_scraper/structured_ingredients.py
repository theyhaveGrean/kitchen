"""Turn ingredient lines into the four product fields used by the display."""

from __future__ import annotations

import re
from collections.abc import Mapping
from fractions import Fraction
from math import isclose
from typing import TypedDict

from ingredient_parser import parse_ingredient
from ingredient_parser.dataclasses import CompositeIngredientAmount, IngredientAmount

_UNIT_LABELS = {
    "teaspoon": "tsp",
    "tablespoon": "tbsp",
    "cup": "cup",
    "gram": "g",
    "kilogram": "kg",
    "milliliter": "mL",
    "liter": "L",
    "ounce": "oz",
    "pound": "lb",
    "fluid_ounce": "fl oz",
}
_LARGER_UNITS = {
    "teaspoon": "tablespoon",
    "tablespoon": "cup",
    "gram": "kilogram",
    "milliliter": "liter",
}
_REQUIRED_NOTE = re.compile(r"\b(?:to taste|as needed|divided|for garnish)\b", re.IGNORECASE)


class StructuredIngredient(TypedDict):
    quantity: str | None
    unit: str | None
    ingredient: str
    preparation_type: str | None


def _quantity(value: Fraction | str) -> str:
    return str(value)


def _normalized_amount(amount: IngredientAmount) -> tuple[str, str | None]:
    """Use parser conversions only when they produce a whole larger unit."""
    quantity = amount.quantity
    unit = amount.unit
    if (
        isinstance(quantity, Fraction)
        and not isinstance(unit, str)
        and not amount.RANGE
        and not amount.APPROXIMATE
    ):
        while target := _LARGER_UNITS.get(str(unit)):
            converted = amount.convert_to(target)
            value = float(converted.quantity)
            nearest = round(value)
            if nearest <= 0 or not isclose(value, nearest, rel_tol=1e-12, abs_tol=1e-12):
                break
            quantity = Fraction(nearest)
            unit = converted.unit
            amount = converted
    result = _quantity(quantity)
    if amount.RANGE:
        result += f"-{_quantity(amount.quantity_max)}"
    if amount.APPROXIMATE:
        result = f"about {result}"
    unit_name = str(unit) if unit else None
    return result, _UNIT_LABELS.get(unit_name, unit_name) if unit_name else None


def parse_ingredient_line(line: str) -> StructuredIngredient:
    """Keep cooking information while omitting parser comments and metadata."""
    parsed = parse_ingredient(line, separate_names=False)
    name = " or ".join(part.text for part in parsed.name).strip()
    if not name:
        return {"quantity": None, "unit": None, "ingredient": line, "preparation_type": None}

    amounts = []
    last_name_index = max(part.starting_index for part in parsed.name)
    for amount in parsed.amount:
        if (
            not isinstance(amount, CompositeIngredientAmount)
            and amount.starting_index > last_name_index
            and not amount.unit
        ):
            name = f"{name} {amount.text}"
        else:
            amounts.append(amount)

    quantity: str | None = None
    unit: str | None = None
    if len(amounts) == 1:
        amount = amounts[0]
        if isinstance(amount, CompositeIngredientAmount):
            quantity = amount.text
        else:
            quantity, unit = _normalized_amount(amount)
    elif amounts:
        quantity = ", ".join(amount.text for amount in amounts)

    preparation = parsed.preparation.text.strip() if parsed.preparation else None
    for note in (parsed.purpose, parsed.comment):
        if note and _REQUIRED_NOTE.search(note.text):
            preparation = ", ".join(part for part in (preparation, note.text.strip()) if part)
    if parsed.size:
        name = f"{parsed.size.text.strip()} {name}"
    return {
        "quantity": quantity,
        "unit": unit,
        "ingredient": name,
        "preparation_type": preparation,
    }


def parse_ingredients(lines: list[str]) -> list[StructuredIngredient]:
    return [parse_ingredient_line(line) for line in lines]


def ingredient_to_line(item: Mapping[str, str | None]) -> str:
    """Reconstruct an ingredient for legacy text normalizers."""
    prefix = " ".join(value for value in (item["quantity"], item["unit"]) if value)
    line = " ".join(value for value in (prefix, item["ingredient"]) if value)
    preparation = item.get("preparation_type") or item.get("preparation")
    return f"{line}, {preparation}" if preparation else line
