"""Deterministic evidence for numeric cooking parameters in source instructions."""

from __future__ import annotations

import re
from fractions import Fraction

from .graph import Duration, Temperature

_NUMBER = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
_RANGE = rf"(?P<low>{_NUMBER})(?:\s*(?:[-–—]|to)\s*(?P<high>{_NUMBER}))?"
_TIME = re.compile(
    rf"{_RANGE}\s*(?:(?:more|additional)\s+)?(?P<unit>seconds?|secs?|minutes?|mins?|hours?|hrs?|days?)\b", re.I
)
_SIGNED_RANGE = _RANGE.replace(_NUMBER, rf"[+-]?{_NUMBER}")
_TEMP = re.compile(
    rf"{_SIGNED_RANGE}\s*(?:°\s*|degrees?\s*)?(?P<unit>Fahrenheit|Celsius|[FC])\b", re.I
)
_SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_WORDS = dict(zip(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred".split(),
    [*range(21), 30, 40, 50, 60, 70, 80, 90, 100], strict=True,
))
_WORD = "|".join(_WORDS)
_WORD_NUMBER = re.compile(rf"\b(?:{_WORD})(?:(?:[ -]+|\s+and\s+)(?:{_WORD}))*\b", re.I)


def _numeric_text(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        value = 0
        for word in re.split(r"[ -]+", match[0].lower()):
            if word == "and":
                continue
            value = max(1, value) * 100 if word == "hundred" else value + _WORDS[word]
        return str(value)

    text = _WORD_NUMBER.sub(replace, text)
    text = re.sub(r"\bhalf\s+(?:an?\s+)?(?=hour|minute|day)", "0.5 ", text, flags=re.I)
    return text


def _number(text: str) -> float:
    return float(sum(Fraction(part) for part in text.split()))


def duration_supported(duration: Duration, text: str) -> bool:
    """Accept explicit endpoints or deterministic conversions, never a guessed midpoint."""
    values = [value for value in (duration.min, duration.nominal, duration.max) if value is not None]
    if not values:
        return True
    evidence: set[float] = set()
    previous_end = -1
    total = 0.0
    text = _numeric_text(text)
    for match in _TIME.finditer(text):
        unit = match["unit"].casefold()
        factor = 1 if unit.startswith("s") else 60 if unit.startswith("m") else 3600 if unit.startswith("h") else 86400
        low = _number(match["low"]) * factor
        evidence.add(low)
        if match["high"]:
            evidence.add(_number(match["high"]) * factor)
            previous_end = -1
        else:
            # "1 hour and 30 minutes" is a single deterministically summable time.
            between = text[previous_end:match.start()].strip().casefold()
            total = total + low if previous_end >= 0 and between in {"", "and"} else low
            evidence.add(total)
            previous_end = match.end()
    factor = _SECONDS[duration.unit] if duration.unit else 1
    return all(any(abs(value * factor - known) < 1e-6 for known in evidence) for value in values)


def temperature_supported(temperature: Temperature, text: str) -> bool:
    values = [value for value in (temperature.min, temperature.nominal, temperature.max) if value is not None]
    if not values:
        return True
    evidence: set[float] = set()
    text = _numeric_text(text)
    for match in _TEMP.finditer(text):
        # An internal target temperature is a completion criterion, not cooking heat.
        prefix = text[max(0, match.start() - 80):match.start()].casefold()
        if re.search(r"(?:internal\s+temperature|until[^.;]*(?:reach|register))[^.;]*$", prefix):
            continue
        for raw in (match["low"], match["high"]):
            if raw is not None:
                value = _number(raw)
                evidence.add((value - 32) * 5 / 9 if match["unit"].lower().startswith("f") else value)
    return all(any(abs(((value - 32) * 5 / 9 if temperature.unit == "F" else value) - known) < 1e-6
                   for known in evidence) for value in values)


def parse_duration(text: str | None) -> Duration:
    """Parse stated timing into structured bounds; perform arithmetic only here."""
    unknown = Duration(min=None, nominal=None, max=None, unit=None)
    if not text:
        return unknown
    normalized = _numeric_text(text)
    matches = list(_TIME.finditer(normalized))
    if not matches:
        return unknown
    first = matches[0]
    unit = next(unit for unit in _SECONDS if first["unit"].lower().startswith(unit[:1]))
    low, high = _number(first["low"]), _number(first["high"]) if first["high"] else None
    if len(matches) > 1 and high is None:
        for previous, following in zip(matches, matches[1:]):
            if normalized[previous.end():following.start()].strip().lower() not in {"", "and"} or following["high"]:
                break
            next_unit = next(unit for unit in _SECONDS if following["unit"].lower().startswith(unit[:1]))
            low += _number(following["low"]) * _SECONDS[next_unit] / _SECONDS[unit]
    prefix = normalized[:first.start()].lower()
    if re.search(r"(?:up to|at most|no more than)\s*$", prefix):
        return Duration(min=None, nominal=None, max=low, unit=unit)  # type: ignore[arg-type]
    if re.search(r"(?:at least|minimum(?: of)?)\s*$", prefix):
        return Duration(min=low, nominal=None, max=None, unit=unit)  # type: ignore[arg-type]
    return Duration(min=low, nominal=None if high is not None else low,
                    max=high if high is not None else low, unit=unit)  # type: ignore[arg-type]


def parse_temperature(text: str | None) -> Temperature:
    unknown = Temperature(min=None, nominal=None, max=None, unit=None)
    if not text:
        return unknown
    match = _TEMP.search(_numeric_text(text))
    if not match:
        return unknown
    low = _number(match["low"])
    high = _number(match["high"]) if match["high"] else None
    return Temperature(min=low, nominal=None if high is not None else low,
                       max=high if high is not None else low,
                       unit="F" if match["unit"].lower().startswith("f") else "C")
