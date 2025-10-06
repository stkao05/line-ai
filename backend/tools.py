import asyncio
import os
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

serper_api_key = os.getenv("SERPER_API_KEY")

if not serper_api_key:
    raise ValueError("SERPER_API_KEY not found in environment variables")


def _build_favicon_url(link: str) -> str | None:
    """Construct a Google favicon service URL for the link's domain."""

    try:
        parsed = urlparse(link)
    except ValueError:
        return None

    if not parsed.scheme or not parsed.netloc:
        return None

    domain_url = f"{parsed.scheme}://{parsed.netloc}"
    return f"https://www.google.com/s2/favicons?sz=64&domain_url={domain_url}"


async def google_search(query: str, num_results: int) -> list:
    timeout = httpx.Timeout(4.0)
    headers = {
        "X-API-KEY": serper_api_key,
        "Content-Type": "application/json",
    }
    requested = min(num_results, 20)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.post(
                "https://google.serper.dev/search",
                headers=headers,
                json={"q": query, "num": requested},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ValueError(f"Serper API request failed: {exc}") from exc

        payload = response.json()

    organic_results = payload.get("organic", []) or []
    news_results = payload.get("news", []) or []
    mixed_results = organic_results + news_results

    collected: list[dict] = []
    for item in mixed_results:
        link = item.get("link")
        if not link:
            continue
        snippet = item.get("snippet") or item.get("snippetHighlighted") or ""
        snippet = snippet.strip() or "Snippet not available."
        favicon = item.get("favicon") or _build_favicon_url(link)
        collected.append(
            {
                "title": item.get("title") or link,
                "link": link,
                "snippet": snippet,
                "favicon": favicon,
            }
        )
        if len(collected) >= num_results:
            break

    return collected


async def google_search_many(
    queries: list[str] | tuple[str, ...], num_results: int
) -> list[dict]:
    """Run multiple Serper searches concurrently and return de-duplicated results.

    - Executes searches for all non-empty queries concurrently.
    - Normalizes and de-duplicates results by URL (first occurrence wins).
    - Each item mirrors `google_search`'s structure: keys `title`, `link`, `snippet`, `favicon`.
    """

    # Normalize and filter out empty queries early
    normalized_queries: list[str] = [
        q.strip() for q in queries if isinstance(q, str) and q.strip()
    ]
    if not normalized_queries:
        return []

    async def _run(q: str) -> list[dict]:
        try:
            return await google_search(q, num_results=num_results)
        except ValueError:
            return []

    results_lists = await asyncio.gather(*(_run(q) for q in normalized_queries))

    # Flatten and de-duplicate by normalized URL
    seen_urls: set[str] = set()
    aggregated: list[dict] = []
    for items in results_lists:
        for item in items:
            link = item.get("link")
            if not isinstance(link, str):
                continue
            url = link.strip()
            if not url or url in seen_urls:
                continue

            title = item.get("title")
            snippet = item.get("snippet")
            favicon = item.get("favicon")

            aggregated.append(
                {
                    "title": (title.strip() if isinstance(title, str) else url) or url,
                    "link": url,
                    "snippet": (snippet or "").strip() or "Snippet not available.",
                    "favicon": (favicon.strip() if isinstance(favicon, str) else None)
                    or _build_favicon_url(url),
                }
            )
            seen_urls.add(url)

    return aggregated


async def fetch_page(url: str, max_chars: int) -> dict[str, str] | None:
    """Fetch and trim textual content from a single web page.

    Returns None when the request cannot be completed successfully."""

    timeout = httpx.Timeout(4.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(separator=" ", strip=True)
    words = text.split()
    content_parts: list[str] = []
    current_len = 0

    for word in words:
        additional = len(word) + (1 if content_parts else 0)
        if current_len + additional > max_chars:
            break
        content_parts.append(word)
        current_len += additional

    trimmed_content = " ".join(content_parts)
    title_tag = soup.find("title")
    page_title = title_tag.text.strip() if title_tag and title_tag.text else url

    return {
        "url": url,
        "title": page_title,
        "content": trimmed_content,
    }
