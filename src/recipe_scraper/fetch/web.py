from __future__ import annotations

try:
    from scrapling.fetchers import StealthyFetcher  # type: ignore
except Exception:
    StealthyFetcher = None

DEFAULT_TIMEOUT = 60


def fetch_with_scrapling(url: str, timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str]:
    """Fetch and render a public page through Scrapling's browser-backed fetcher."""
    if StealthyFetcher is None:
        raise RuntimeError(
            'Scrapling is required. Install with: pip install "recipe-scraper[fetch]" '
            'and then run: scrapling install'
        )
    page = StealthyFetcher.fetch(
        url,
        headless=True,
        network_idle=False,
        google_search=True,
        block_ads=True,
        timeout=max(0, timeout) * 1000,
    )
    status = getattr(page, "status", None)
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
