# %%
import asyncio
import os
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional, Sequence, Set
from uuid import uuid4

from autogen_agentchat.agents import AssistantAgent, BaseChatAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.messages import (
    BaseChatMessage,
    BaseTextChatMessage,
    ModelClientStreamingChunkEvent,
    StructuredMessage,
)
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient
from message import (
    AnswerDeltaMessage,
    AnswerMessage,
    FetchEndMessage,
    FetchStartMessage,
    Page,
    RankEndMessage,
    RankStartMessage,
    SearchEndMessage,
    SearchStartMessage,
    StreamMessage,
    TurnStartMessage,
)
from pydantic import BaseModel, ValidationError
from tools import fetch_page, google_search

openai_api_key = os.getenv("OPENAI_API_KEY")
model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_api_key)

# gemini_api_key = os.getenv("GEMINI_API_KEY")
# gemini_model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
# model_client = OpenAIChatCompletionClient(model=gemini_model, api_key=gemini_api_key)


@dataclass
class ConversationState:
    team: RoundRobinGroupChat
    lock: asyncio.Lock


# Keeps in-memory state per conversation. Safe under single-process lifetime.
_conversation_states: Dict[str, ConversationState] = {}


class SearchQuery(BaseModel):
    query: str


SearchQueryMessage = StructuredMessage[SearchQuery]


class SearchCandidateItem(BaseModel):
    title: str
    url: str
    snippet: str
    favicon: Optional[str] = None


class SearchCandidates(BaseModel):
    query: str
    candidates: List[SearchCandidateItem]


SearchCandidatesMessage = StructuredMessage[SearchCandidates]


class RankedSearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str
    reason: str
    favicon: Optional[str] = None


class RankedSearchResults(BaseModel):
    selections: List[RankedSearchResultItem]


RankedSearchResultsMessage = StructuredMessage[RankedSearchResults]


class SearchResultItem(BaseModel):
    title: str
    url: str
    favicon: Optional[str] = None
    snippet: str
    detail_summary: str


class SearchResult(BaseModel):
    results: List[SearchResultItem]


SearchResultMessage = StructuredMessage[SearchResult]


class GoogleSearchExecutorAgent(BaseChatAgent):
    def __init__(self, name: str, *, description: str, num_results: int = 20) -> None:
        super().__init__(name, description=description)
        self._num_results = num_results

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (SearchCandidatesMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        query_message: Optional[SearchQueryMessage] = None
        for message in reversed(messages):
            if isinstance(message, SearchQueryMessage):
                query_message = message
                break

        query_text = ""
        if query_message is not None:
            query_text = query_message.content.query.strip()

        candidates: List[SearchCandidateItem] = []

        if query_text:
            try:
                raw_results = await google_search(
                    query=query_text, num_results=self._num_results
                )
            except ValueError:
                raw_results = []
            else:
                for item in raw_results:
                    url = item.get("link")
                    if not isinstance(url, str) or not url.strip():
                        continue

                    title = item.get("title")
                    snippet = item.get("snippet")
                    favicon = item.get("favicon")

                    candidate = SearchCandidateItem(
                        title=title.strip()
                        if isinstance(title, str) and title.strip()
                        else url,
                        url=url.strip(),
                        snippet=(snippet or "Snippet not available.").strip(),
                        favicon=favicon.strip()
                        if isinstance(favicon, str) and favicon.strip()
                        else None,
                    )
                    candidates.append(candidate)

        structured_message = SearchCandidatesMessage(
            content=SearchCandidates(query=query_text, candidates=candidates),
            source=self.name,
        )

        return Response(chat_message=structured_message)

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        return None


class PageFetchAgent(BaseChatAgent):
    def __init__(
        self,
        name: str,
        *,
        description: str,
        max_chars: int = 4000,
    ) -> None:
        super().__init__(name, description=description)
        self._max_chars = max_chars

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (SearchResultMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        ranked_message: Optional[RankedSearchResultsMessage] = None
        for message in reversed(messages):
            if isinstance(message, RankedSearchResultsMessage):
                ranked_message = message
                break

        def _clean(text: Optional[str]) -> str:
            return text.strip() if isinstance(text, str) else ""

        results: List[SearchResultItem] = []

        if ranked_message is not None:

            async def fetch(
                selection: RankedSearchResultItem,
            ) -> tuple[RankedSearchResultItem, Dict[str, str]] | None:
                url = _clean(selection.url)
                if not url:
                    return None

                try:
                    payload = await fetch_page(url=url, max_chars=self._max_chars)
                except Exception as exc:  # pragma: no cover - defensive guardrail
                    payload = {
                        "url": url,
                        "title": url,
                        "content": f"ERROR: failed to fetch page content ({exc})",
                    }
                else:
                    if payload is None:
                        payload = {
                            "url": url,
                            "title": url,
                            "content": "Content unavailable.",
                        }

                if not isinstance(payload, dict):
                    payload = {
                        "url": url,
                        "title": url,
                        "content": "Content unavailable.",
                    }

                return selection, payload

            payloads = await asyncio.gather(
                *(fetch(selection) for selection in ranked_message.content.selections),
                return_exceptions=False,
            )

            for item in payloads:
                if item is None:
                    continue

                selection, payload = item
                url = _clean(selection.url)
                fetched_url = _clean(payload.get("url")) or url
                title = (
                    _clean(payload.get("title"))
                    or _clean(selection.title)
                    or fetched_url
                )
                content = _clean(payload.get("content"))
                snippet_seed = _clean(selection.snippet)
                snippet = snippet_seed or (content[:200].strip() if content else "")
                favicon = _clean(selection.favicon) or None

                results.append(
                    SearchResultItem(
                        title=title or fetched_url,
                        url=fetched_url or url,
                        favicon=favicon,
                        snippet=snippet or "Snippet not available.",
                        detail_summary=content or "Content unavailable.",
                    )
                )

        structured_message = SearchResultMessage(
            content=SearchResult(results=results),
            source=self.name,
        )

        return Response(chat_message=structured_message)

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        return None


def create_team():
    query_system_message = """
    You are a **search query planner**.

    - Review the user's question and craft the single most effective Google search query.
    - Respond with a `SearchQuery` structured object containing the final query string in the `query` field.
    - Focus on precision keywords that will surface authoritative, up-to-date sources.
    - Do **not** answer the user's question directly or call any tools.
    - Keep your output concise; do not add commentary outside of the structured response.
    """

    search_query_agent = AssistantAgent(
        name="search_query_agent",
        model_client=model_client,
        output_content_type=SearchQuery,
        description="Generate targeted Google search queries based on the user request",
        system_message=query_system_message,
    )

    google_search_agent = GoogleSearchExecutorAgent(
        name="google_search_agent",
        description="Run Serper searches and emit structured candidate results",
        num_results=20,
    )

    ranking_system_message = """
    You are a **search ranking analyst**.

    - Review the user's question and the `SearchCandidates` shared by the search specialist.
    - Select the **top 3** entries that are most likely to answer the question.
    - For each selection, provide a concise rationale in the `reason` field explaining why it is relevant.
    - Respond with a `RankedSearchResults` structured object containing a `selections` list.
    - Preserve the `title`, `url`, `snippet`, and `favicon` from the chosen candidates; do not fabricate information.
    - Do not call external tools or attempt to fetch page content.
    - Do not answer the user directly.
    """

    search_rank_agent = AssistantAgent(
        name="search_rank_agent",
        model_client=model_client,
        output_content_type=RankedSearchResults,
        description="Select the most relevant websites from the candidate list",
        system_message=ranking_system_message,
    )

    page_fetch_agent = PageFetchAgent(
        name="page_fetch_agent",
        description="Retrieve page content for ranked search selections",
        max_chars=4000,
    )

    termination = TextMentionTermination("TERMINATE", sources=["report_agent"])

    report_system_message = """
    You are a helpful report-writing assistant.

    - Review the conversation, especially the fetched page content provided by the research specialist, and compose a comprehensive answer to the user.
    - Synthesize key findings, compare sources when helpful, and acknowledge any gaps or uncertainties.
    - Present the answer in clear sections or paragraphs as appropriate.
    - When you finish, append the token `TERMINATE` on a new line to signal completion.
    """

    report_agent = AssistantAgent(
        name="report_agent",
        model_client=model_client,
        description="Generate a summary report based on the research findings",
        system_message=report_system_message,
        model_client_stream=True,
    )

    team = RoundRobinGroupChat(
        [
            search_query_agent,
            google_search_agent,
            search_rank_agent,
            page_fetch_agent,
            report_agent,
        ],
        custom_message_types=[
            SearchQueryMessage,
            SearchCandidatesMessage,
            RankedSearchResultsMessage,
            SearchResultMessage,
        ],
        termination_condition=termination,
    )

    return team


async def ask(
    user_message: str, conversation_id: Optional[str] = None
) -> AsyncIterator[StreamMessage]:
    if not user_message or not user_message.strip():
        raise ValueError("user_message must not be empty")

    normalized_conversation_id = (
        conversation_id.strip() if conversation_id and conversation_id.strip() else None
    )
    conv_id = normalized_conversation_id or uuid4().hex

    state = _conversation_states.get(conv_id)
    if state is None:
        state = ConversationState(team=create_team(), lock=asyncio.Lock())
        _conversation_states[conv_id] = state

    if state.lock.locked():
        raise RuntimeError(
            f"conversation '{conv_id}' is already processing another request"
        )

    await state.lock.acquire()
    try:
        search_started: Set[str] = set()
        search_completed: Set[str] = set()
        rank_started = False
        fetch_announced: Set[str] = set()
        answer_chunks: List[str] = []
        fallback_segments: List[str] = []
        latest_citation_pages: List[Page] = []

        def build_page(
            url: str,
            *,
            title: Optional[str] = None,
            snippet: Optional[str] = None,
            favicon: Optional[str] = None,
            snippet_maxlen: Optional[int] = 100,
        ) -> Page | None:
            payload: Dict[str, Optional[str]] = {"url": url}
            if title:
                payload["title"] = title
            if snippet:
                payload["snippet"] = snippet[:snippet_maxlen] if snippet_maxlen else snippet
            if favicon:
                payload["favicon"] = favicon

            try:
                return Page.model_validate(payload)
            except ValidationError:
                return None

        def strip_termination_token(text: str) -> str:
            trimmed = text.rstrip()
            if trimmed.endswith("TERMINATE"):
                trimmed = trimmed[: -len("TERMINATE")].rstrip()
            return trimmed

        yield TurnStartMessage(
            type="turn.start",
            conversation_id=conv_id,
        )

        async for event in state.team.run_stream(task=user_message):
            if isinstance(event, SearchQueryMessage):
                query = event.content.query.strip()
                if query and query not in search_started:
                    search_started.add(query)
                    yield SearchStartMessage(type="search.start", query=query)
                continue

            if isinstance(event, SearchCandidatesMessage):
                query = event.content.query.strip()

                if query and query not in search_started:
                    search_started.add(query)
                    yield SearchStartMessage(type="search.start", query=query)

                if query and query not in search_completed:
                    search_completed.add(query)
                    yield SearchEndMessage(
                        type="search.end",
                        query=query,
                        results=len(event.content.candidates),
                    )

                if not rank_started:
                    rank_started = True
                    yield RankStartMessage(type="rank.start")

                continue

            if isinstance(event, RankedSearchResultsMessage):
                if not rank_started:
                    rank_started = True
                    yield RankStartMessage(type="rank.start")

                ranked_pages: List[Page] = []
                seen_rank_urls: Set[str] = set()
                fetch_start_pages: List[Page] = []
                for item in event.content.selections:
                    url = item.url.strip()
                    if not url or url in seen_rank_urls:
                        continue

                    ranked_page = build_page(
                        url,
                        title=item.title.strip() if item.title else None,
                        snippet=item.snippet.strip() if item.snippet else None,
                        favicon=item.favicon.strip() if item.favicon else None,
                    )
                    if ranked_page is not None:
                        seen_rank_urls.add(url)
                        ranked_pages.append(ranked_page)

                        if url not in fetch_announced:
                            fetch_announced.add(url)
                            fetch_start_pages.append(ranked_page)

                yield RankEndMessage(type="rank.end", pages=ranked_pages)

                if fetch_start_pages:
                    yield FetchStartMessage(type="fetch.start", pages=fetch_start_pages)

                continue

            if isinstance(event, SearchResultMessage):
                fetched_pages: List[Page] = []
                seen_fetch_urls: Set[str] = set()
                for result in event.content.results:
                    url = result.url.strip()
                    if not url or url in seen_fetch_urls:
                        continue

                    detail = (result.detail_summary or result.snippet or "").strip()
                    fetched_page = build_page(
                        url,
                        title=result.title.strip() if result.title else None,
                        snippet=detail or None,
                        favicon=result.favicon.strip() if result.favicon else None,
                    )
                    if fetched_page is not None:
                        seen_fetch_urls.add(url)
                        fetched_pages.append(fetched_page)

                latest_citation_pages = fetched_pages
                yield FetchEndMessage(
                    type="fetch.end",
                    pages=fetched_pages or None,
                )

                continue

            if isinstance(event, ModelClientStreamingChunkEvent):
                if event.source == "report_agent":
                    content = event.content or ""
                    if content:
                        answer_chunks.append(content)
                        yield AnswerDeltaMessage(type="answer-delta", delta=content)
                continue

            if isinstance(event, BaseTextChatMessage) and event.source == "report_agent":
                # Capture the final report for fallback when streaming chunks are unavailable.
                if event.content:
                    fallback_segments.append(event.content)
                continue

            if isinstance(event, TaskResult):
                final_answer = strip_termination_token("".join(answer_chunks))

                if not final_answer:
                    if fallback_segments:
                        final_answer = strip_termination_token("".join(fallback_segments))

                if not final_answer:
                    report_segments: List[str] = []
                    for message in event.messages:
                        if (
                            isinstance(message, BaseTextChatMessage)
                            and message.source == "report_agent"
                        ):
                            report_segments.append(message.content)
                    final_answer = strip_termination_token("".join(report_segments))

                yield AnswerMessage(
                    type="answer",
                    answer=final_answer,
                    citations=latest_citation_pages or None,
                )
                break
    finally:
        state.lock.release()


# %%
if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        question = "Who won the UEFA Champions League in 2023?"
        print(f"Running trial ask() for: {question}")
        conversation_id: str | None = None
        async for message in ask(question):
            print(message.model_dump())
            if isinstance(message, TurnStartMessage):
                conversation_id = message.conversation_id

        if conversation_id:
            follow_up = "Who did they face in the final?"
            print(f"\nRunning follow-up ask() for: {follow_up}")
            async for message in ask(follow_up, conversation_id=conversation_id):
                print(message.model_dump())

    asyncio.run(_demo())
