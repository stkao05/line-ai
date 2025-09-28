import asyncio
import os

import httpx
from bs4 import BeautifulSoup

api_key = os.getenv("GOOGLE_API_KEY")
search_engine_id = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

if not api_key or not search_engine_id:
    raise ValueError("API key or Search Engine ID not found in environment variables")


async def google_search(query: str, num_results: int, max_chars: int) -> list:
    """Execute a Google search and fetch result page bodies concurrently."""

    timeout = httpx.Timeout(2.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:

        async def _get_page_content(url: str) -> str | None:
            try:
                response = await client.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError:
                return None
            except httpx.HTTPError:
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
            words = text.split()
            content = ""
            for word in words:
                if len(content) + len(word) + 1 > max_chars:
                    break
                content += " " + word
            return content.strip()

        url = "https://customsearch.googleapis.com/customsearch/v1"
        params = {
            "key": str(api_key),
            "cx": str(search_engine_id),
            "q": str(query),
            "num": str(num_results),
        }

        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
        results = payload.get("items", [])

        async def _enrich(item: dict) -> dict | None:
            body = await _get_page_content(item["link"])
            if body is None:
                return None
            return {
                "title": item["title"],
                "link": item["link"],
                "snippet": item["snippet"],
                "body": body,
            }

        tasks = [_enrich(item) for item in results]
        enriched = await asyncio.gather(*tasks)
        return [item for item in enriched if item is not None]
