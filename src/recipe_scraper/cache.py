"""Versioned, independent stage caches with atomic writes and conservative URL keys."""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

EXTRACTOR_VERSION = "static-first-v1"
_TRACKING = {"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("Expected a public HTTP(S) URL without credentials")
    host = parts.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    if parts.port and (scheme, parts.port) not in {("http", 80), ("https", 443)}:
        host += f":{parts.port}"
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING
    ]
    return urlunsplit((scheme, host, parts.path.rstrip("/") or "/", urlencode(query), ""))


def page_canonical_url(html: str, final_url: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("link", rel=lambda value: value and "canonical" in value)
    if tag and tag.get("href"):
        candidate = urljoin(final_url, str(tag["href"]))
        if urlsplit(candidate).hostname == urlsplit(final_url).hostname:
            return normalize_url(candidate)
    return normalize_url(final_url)


def content_hash(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def cache_root() -> Path:
    return Path(os.getenv("RECIPE_CACHE_DIR", "benchmarks/results/cache"))


def read_record(path: Path, key: str, *, ttl: float | None = None) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("cache_key") != key:
            return None
        if ttl is not None and (ttl <= 0 or time.time() - float(data["stored_at"]) > ttl):
            return None
        return data
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_record(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps({**data, "stored_at": time.time()}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
