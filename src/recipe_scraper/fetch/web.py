from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import Request, urlopen

DEFAULT_TIMEOUT = 60


class FetchBlocked(RuntimeError):
    """Do not use browser fallback to evade an explicit access denial."""


def fetch_static(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    request = Request(url, headers={"User-Agent": "RecipeScraper/0.2", "Accept": "text/html"})
    try:
        with urlopen(request, timeout=timeout if timeout > 0 else None) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace"), response.geturl()
    except HTTPError as exc:
        if exc.code in {401, 403, 429}:
            raise FetchBlocked(f"FETCH_BLOCKED: HTTP {exc.code}") from exc
        raise


def fetch_with_scrapling(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """Fetch and render a public page through Scrapling's browser-backed fetcher."""
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError as exc:
        raise RuntimeError(
            'Scrapling is required. Install with: pip install "recipe-scraper[fetch]" '
            'and then run: scrapling install'
        ) from exc
    page = StealthyFetcher.fetch(
        url,
        headless=True,
        network_idle=False,
        google_search=False,
        solve_cloudflare=False,
        block_ads=True,
        timeout=max(0, timeout) * 1000,
    )
    status = getattr(page, "status", None)
    if status in {401, 403, 429}:
        raise FetchBlocked(f"FETCH_BLOCKED: HTTP {status}")
    if status in {404, 410}:
        raise RuntimeError(f"HTTP error {status}: page not found")
    html_text = getattr(page, "html_content", None)
    if callable(html_text):
        html_text = html_text()
    if not html_text:
        body = getattr(page, "body", b"")
        if isinstance(body, bytes):
            html_text = body.decode("utf-8", errors="replace")
        elif body:
            html_text = str(body)
        else:
            html_text = str(page)
    final_url = str(getattr(page, "url", None) or url)
    if not html_text or len(html_text) < 100:
        raise RuntimeError(f"Scrapling returned no usable HTML (HTTP status {status or 'unknown'}).")
    return html_text, final_url
