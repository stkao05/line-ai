# %%
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Dict, List, Literal, Optional, Sequence, Set
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
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient
from message import (
    AnswerMessage,
    Page,
    StepAnswerDeltaMessage,
    StepAnswerEndMessage,
    StepAnswerStartMessage,
    StepEndMessage,
    StepFetchEndMessage,
    StepFetchStartMessage,
    StepStartMessage,
    StepStatusMessage,
    StreamMessage,
    TurnStartMessage,
)
from pydantic import BaseModel, ValidationError
from tools import fetch_page, google_search

openai_api_key = os.getenv("OPENAI_API_KEY")
general_model = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_api_key)
quick_model = OpenAIChatCompletionClient(model="gpt-4o-mini", api_key=openai_api_key)
coding_model = OpenAIChatCompletionClient(model="gpt-5", api_key=openai_api_key)


@dataclass
class ConversationState:
    team: GraphFlow
    lock: asyncio.Lock


# Keeps in-memory state per conversation. Safe under single-process lifetime.
_conversation_states: Dict[str, ConversationState] = {}


class ConversationSession:
    """Manage conversation lookup, creation, and locking."""

    def __init__(self, conversation_id: Optional[str]) -> None:
        normalized = (
            conversation_id.strip()
            if conversation_id and conversation_id.strip()
            else None
        )
        self._requested_id = normalized
        self.conversation_id: Optional[str] = None
        self.state: Optional[ConversationState] = None

    async def __aenter__(self) -> "ConversationSession":
        conv_id = self._requested_id or uuid4().hex
        state = _conversation_states.get(conv_id)
        if state is None:
            state = ConversationState(team=create_team(), lock=asyncio.Lock())
            _conversation_states[conv_id] = state

        if state.lock.locked():
            raise RuntimeError(
                f"conversation '{conv_id}' is already processing another request"
            )

        await state.lock.acquire()
        self.conversation_id = conv_id
        self.state = state
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.state is not None:
            self.state.lock.release()


class StepProgressTracker:
    """Track search step lifecycle and query-specific messaging state."""

    def __init__(self, *, title: str) -> None:
        self._title = title
        self._open = False
        self._started_queries: Set[str] = set()
        self._status_announced: Set[str] = set()
        self._completed_queries: Set[str] = set()
        self._completed_without_query = False

    @property
    def title(self) -> str:
        return self._title

    @property
    def is_open(self) -> bool:
        return self._open

    def start_step(self, description: str) -> List[StreamMessage]:
        if self._open:
            return []

        self._open = True
        return [
            StepStartMessage(
                type="step.start",
                title=self._title,
                description=description,
            )
        ]

    def record_query(self, query: str) -> bool:
        normalized = query.strip()
        if not normalized or normalized in self._started_queries:
            return False

        self._started_queries.add(normalized)
        return True

    def emit_status(self, query: str, description: str) -> List[StreamMessage]:
        normalized = query.strip()
        if not normalized or normalized in self._status_announced:
            return []

        self._status_announced.add(normalized)
        return [
            StepStatusMessage(
                type="step.status",
                title=self._title,
                description=description,
            )
        ]

    def complete_step(
        self, query: Optional[str], description: str
    ) -> List[StreamMessage]:
        normalized = query.strip() if query else ""
        if normalized:
            if normalized in self._completed_queries:
                return []
            self._completed_queries.add(normalized)
        else:
            if self._completed_without_query:
                return []
            self._completed_without_query = True

        self._open = False
        return [
            StepEndMessage(
                type="step.end",
                title=self._title,
                description=description,
            )
        ]


class EventProcessor:
    """Dispatch agent events to dedicated handlers for streaming output."""

    def __init__(
        self,
        *,
        planning_title: str,
        search_tracker: StepProgressTracker,
        search_prepare_description: str,
        rank_step_title: str,
        fetch_step_title: str,
        coding_step_title: str,
        answer_step_title: str,
    ) -> None:
        self._planning_title = planning_title
        self._planning_step_open = False
        self._search_tracker = search_tracker
        self._search_prepare_description = search_prepare_description
        self._rank_step_title = rank_step_title
        self._fetch_step_title = fetch_step_title
        self._coding_step_title = coding_step_title
        self._answer_step_title = answer_step_title

        self._rank_step_started = False
        self._rank_step_completed = False
        self._fetch_announced: Set[str] = set()
        self._answer_chunks: List[str] = []
        self._fallback_segments: List[str] = []
        self._latest_citation_pages: List[Page] = []
        self._active_research_plan: Optional[ResearchPlan] = None
        self._answer_step_description: Optional[str] = None
        self._answer_step_started = False
        self._answer_step_completed = False
        self._coding_step_open = False
        self._final_agent_sources: Set[str] = {
            "report_agent",
            "quick_answer_agent",
            "coding_agent",
        }
        self.finished = False

    def set_planning_active(self, active: bool) -> None:
        self._planning_step_open = active

    async def process_event(self, event: object) -> List[StreamMessage]:
        handler = self._resolve_handler(event)
        if handler is None:
            return []

        result = handler(event)
        if asyncio.iscoroutine(result):
            result = await result
        if result is None:
            return []
        if isinstance(result, list):
            return result
        if isinstance(result, tuple):
            return list(result)
        return [result]

    def _resolve_handler(self, event: object):
        event_type = type(event)

        handler = getattr(self, f"handle_{event_type.__name__}", None)
        if handler is not None:
            return handler

        if isinstance(event, StructuredMessage):
            content = getattr(event, "content", None)
            if content is not None:
                content_handler = getattr(
                    self, f"handle_{type(content).__name__}Message", None
                )
                if content_handler is not None:
                    return content_handler

        for cls in event_type.mro()[1:]:
            handler = getattr(self, f"handle_{cls.__name__}", None)
            if handler is not None:
                return handler
        return None

    # Event handlers -------------------------------------------------

    def handle_RoutePlanMessage(self, event: RoutePlanMessage) -> List[StreamMessage]:
        route = event.content.route
        messages: List[StreamMessage] = []

        if route == "quick_answer":
            self._final_agent_sources = {"quick_answer_agent"}
            end_description = (
                "Quick answer selected – responding directly using existing knowledge."
            )
            self._answer_step_description = (
                "Drafting a direct reply without additional research."
            )
        elif route == "coding":
            self._final_agent_sources = {"coding_agent"}
            end_description = (
                "Coding support engaged – focusing on implementation guidance."
            )
            self._answer_step_description = (
                "Producing code-focused explanations and solutions."
            )
            if not self._coding_step_open:
                self._coding_step_open = True
                messages.append(
                    StepStartMessage(
                        type="step.start",
                        title=self._coding_step_title,
                        description="Coding agent is thinking through the implementation details.",
                    )
                )
        else:
            self._final_agent_sources = {"report_agent"}
            end_description = "Deep dive research selected – gathering sources for a comprehensive response."
            self._answer_step_description = (
                "Synthesizing findings from external research."
            )
            messages.extend(
                self._search_tracker.start_step(self._search_prepare_description)
            )

        if self._planning_step_open:
            messages.append(
                StepEndMessage(
                    type="step.end",
                    title=self._planning_title,
                    description=end_description,
                )
            )
            self._planning_step_open = False

        return messages

    def handle_ResearchPlanMessage(
        self, event: ResearchPlanMessage
    ) -> List[StreamMessage]:
        self._active_research_plan = event.content
        return []

    def handle_SearchQueryMessage(
        self, event: SearchQueryMessage
    ) -> List[StreamMessage]:
        query = event.content.query.strip()
        if not query:
            return []

        messages: List[StreamMessage] = []
        if self._search_tracker.record_query(query):
            messages.extend(
                self._search_tracker.start_step(f'Searching for "{query}".')
            )

        messages.extend(
            self._search_tracker.emit_status(query, f'Searching with "{query}".')
        )
        return messages

    def handle_SearchCandidatesMessage(
        self, event: SearchCandidatesMessage
    ) -> List[StreamMessage]:
        query = event.content.query.strip()
        candidate_count = len(event.content.candidates)
        messages: List[StreamMessage] = []

        if query:
            if self._search_tracker.record_query(query):
                messages.extend(
                    self._search_tracker.start_step(f'Searching for "{query}".')
                )
            messages.extend(
                self._search_tracker.emit_status(query, f'Searching with "{query}".')
            )
            messages.extend(
                self._search_tracker.complete_step(
                    query, f'Found {candidate_count} candidates for "{query}".'
                )
            )
        else:
            messages.extend(
                self._search_tracker.complete_step(
                    None,
                    ("Found {count} candidates without a specific query.").format(
                        count=candidate_count
                    ),
                )
            )

        messages.extend(self._ensure_rank_step_started())
        return messages

    def handle_RankedSearchResultsMessage(
        self, event: RankedSearchResultsMessage
    ) -> List[StreamMessage]:
        messages: List[StreamMessage] = []
        messages.extend(self._ensure_rank_step_started())

        ranked_pages: List[Page] = []
        seen_rank_urls: Set[str] = set()
        fetch_start_pages: List[Page] = []
        rank_limit: Optional[int] = None
        fetch_limit: Optional[int] = None

        if self._active_research_plan is not None:
            rank_limit = max(0, self._active_research_plan.rank_top_k)
            fetch_limit = max(0, self._active_research_plan.fetch_page_limit)

        for item in event.content.selections:
            url = item.url.strip()
            if not url or url in seen_rank_urls:
                continue

            ranked_page = self._build_page(
                url,
                title=item.title.strip() if item.title else None,
                snippet=item.snippet.strip() if item.snippet else None,
                favicon=item.favicon.strip() if item.favicon else None,
            )
            if ranked_page is None:
                continue

            seen_rank_urls.add(url)
            if rank_limit is None or len(ranked_pages) < rank_limit:
                ranked_pages.append(ranked_page)

            if url not in self._fetch_announced and (
                fetch_limit is None or len(fetch_start_pages) < fetch_limit
            ):
                self._fetch_announced.add(url)
                fetch_start_pages.append(ranked_page)

        if not self._rank_step_completed:
            messages.append(
                StepEndMessage(
                    type="step.end",
                    title=self._rank_step_title,
                    description=f"Selected {len(ranked_pages)} pages for deeper research.",
                )
            )
            self._rank_step_completed = True

        if fetch_start_pages:
            messages.append(
                StepFetchStartMessage(
                    type="step.fetch.start",
                    title=self._fetch_step_title,
                    pages=fetch_start_pages,
                )
            )

        return messages

    def handle_SearchResultMessage(
        self, event: SearchResultMessage
    ) -> List[StreamMessage]:
        fetched_pages: List[Page] = []
        seen_fetch_urls: Set[str] = set()
        fetch_limit: Optional[int] = None

        if self._active_research_plan is not None:
            fetch_limit = max(0, self._active_research_plan.fetch_page_limit)

        for result in event.content.results:
            url = result.url.strip()
            if not url or url in seen_fetch_urls:
                continue

            detail = (result.detail_summary or result.snippet or "").strip()
            fetched_page = self._build_page(
                url,
                title=result.title.strip() if result.title else None,
                snippet=detail or None,
                favicon=result.favicon.strip() if result.favicon else None,
            )
            if fetched_page is None:
                continue

            seen_fetch_urls.add(url)
            if fetch_limit == 0:
                break
            if fetch_limit is None or len(fetched_pages) < fetch_limit:
                fetched_pages.append(fetched_page)
            if fetch_limit is not None and len(fetched_pages) >= fetch_limit:
                break

        self._latest_citation_pages = fetched_pages
        return [
            StepFetchEndMessage(
                type="step.fetch.end",
                title=self._fetch_step_title,
                pages=fetched_pages,
            )
        ]

    def handle_ModelClientStreamingChunkEvent(
        self, event: ModelClientStreamingChunkEvent
    ) -> List[StreamMessage]:
        if event.source not in self._final_agent_sources:
            return []

        content = event.content or ""
        if not content:
            return []

        messages: List[StreamMessage] = []
        if self._coding_step_open:
            messages.append(
                StepEndMessage(
                    type="step.end",
                    title=self._coding_step_title,
                    description="Coding approach finalized – composing response.",
                )
            )
            self._coding_step_open = False

        messages.extend(self._ensure_answer_step_started())
        self._answer_chunks.append(content)
        messages.append(
            StepAnswerDeltaMessage(
                type="step.answer.delta",
                title=self._answer_step_title,
                delta=content,
            )
        )
        return messages

    def handle_BaseTextChatMessage(
        self, event: BaseTextChatMessage
    ) -> List[StreamMessage]:
        if event.source in self._final_agent_sources and event.content:
            self._fallback_segments.append(event.content)
        return []

    def handle_TaskResult(self, event: TaskResult) -> List[StreamMessage]:
        messages: List[StreamMessage] = []

        if self._coding_step_open:
            messages.append(
                StepEndMessage(
                    type="step.end",
                    title=self._coding_step_title,
                    description="Coding approach finalized – composing response.",
                )
            )
            self._coding_step_open = False

        final_answer = self._strip_termination_token("".join(self._answer_chunks))
        if not final_answer and self._fallback_segments:
            final_answer = self._strip_termination_token(
                "".join(self._fallback_segments)
            )

        if not final_answer:
            report_segments: List[str] = []
            for message in event.messages:
                if (
                    isinstance(message, BaseTextChatMessage)
                    and message.source in self._final_agent_sources
                ):
                    report_segments.append(message.content)
            final_answer = self._strip_termination_token("".join(report_segments))

        messages.extend(self._ensure_answer_step_started())

        if not self._answer_step_completed:
            messages.append(
                StepAnswerEndMessage(
                    type="step.answer.end",
                    title=self._answer_step_title,
                )
            )
            self._answer_step_completed = True

        messages.append(
            AnswerMessage(
                type="answer",
                answer=final_answer,
                citations=self._latest_citation_pages or None,
            )
        )

        self.finished = True
        return messages

    # Helper utilities ----------------------------------------------

    def _ensure_answer_step_started(self) -> List[StreamMessage]:
        if self._answer_step_started:
            return []

        self._answer_step_started = True
        return [
            StepAnswerStartMessage(
                type="step.answer.start",
                title=self._answer_step_title,
                description=self._answer_step_description,
            )
        ]

    def _ensure_rank_step_started(self) -> List[StreamMessage]:
        if self._rank_step_started:
            return []

        self._rank_step_started = True
        return [
            StepStartMessage(
                type="step.start",
                title=self._rank_step_title,
                description="Prioritizing pages to review in depth.",
            )
        ]

    @staticmethod
    def _strip_termination_token(text: str) -> str:
        trimmed = text.rstrip()
        if trimmed.endswith("TERMINATE"):
            trimmed = trimmed[: -len("TERMINATE")].rstrip()
        return trimmed

    @staticmethod
    def _build_page(
        url: str,
        *,
        title: Optional[str] = None,
        snippet: Optional[str] = None,
        favicon: Optional[str] = None,
        snippet_maxlen: Optional[int] = 100,
    ) -> Optional[Page]:
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


class RoutePlan(BaseModel):
    route: Literal["quick_answer", "deep_dive", "coding"]


RoutePlanMessage = StructuredMessage[RoutePlan]


class ResearchPlan(BaseModel):
    queries: List[str]
    rank_top_k: int
    fetch_page_limit: int


ResearchPlanMessage = StructuredMessage[ResearchPlan]


class TodayDate(BaseModel):
    iso_date: str
    human_readable: str
    timezone: str


TodayDateMessage = StructuredMessage[TodayDate]


def _latest_message_of_type(
    messages: Sequence[BaseChatMessage], message_type: type[BaseChatMessage]
) -> Optional[BaseChatMessage]:
    for message in reversed(messages):
        if isinstance(message, message_type):
            return message
    return None


class TodayDateAgent(BaseChatAgent):
    def __init__(self, name: str, *, description: str) -> None:
        super().__init__(name, description=description)
        self._last_announced_iso: Optional[str] = None

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TodayDateMessage,)

    async def on_messages(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> Response:
        current_utc = datetime.now(timezone.utc)
        iso_date = current_utc.date().isoformat()

        if self._last_announced_iso == iso_date:
            return Response()

        self._last_announced_iso = iso_date

        human_readable = current_utc.strftime("%B %d, %Y")
        structured_message = TodayDateMessage(
            content=TodayDate(
                iso_date=iso_date,
                human_readable=human_readable,
                timezone="UTC",
            ),
            source=self.name,
        )

        return Response(chat_message=structured_message)

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        self._last_announced_iso = None


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
        query_message = _latest_message_of_type(messages, SearchQueryMessage)
        plan_message = _latest_message_of_type(messages, ResearchPlanMessage)

        query_text = ""
        if query_message is not None:
            query_text = query_message.content.query.strip()
        elif isinstance(plan_message, ResearchPlanMessage):
            for candidate in plan_message.content.queries:
                candidate_query = candidate.strip()
                if candidate_query:
                    query_text = candidate_query
                    break

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
        plan_message = _latest_message_of_type(messages, ResearchPlanMessage)
        fetch_limit: Optional[int] = None
        if isinstance(plan_message, ResearchPlanMessage):
            fetch_limit = max(0, plan_message.content.fetch_page_limit)

        ranked_message: Optional[RankedSearchResultsMessage] = None
        for message in reversed(messages):
            if isinstance(message, RankedSearchResultsMessage):
                ranked_message = message
                break

        def _clean(text: Optional[str]) -> str:
            return text.strip() if isinstance(text, str) else ""

        results: List[SearchResultItem] = []

        if ranked_message is not None:
            selections = list(ranked_message.content.selections)
            if fetch_limit is not None:
                if fetch_limit == 0:
                    selections = []
                else:
                    selections = selections[:fetch_limit]

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
                *(fetch(selection) for selection in selections),
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
    current_utc = datetime.now(timezone.utc)
    iso_date = current_utc.date().isoformat()
    human_date = current_utc.strftime("%B %d, %Y")

    router_system_message = f"""
    You are the **routing planner** for a retrieval assistant. Today's date is {human_date} (UTC {iso_date}).

    Responsibilities:
    - Inspect the latest user request and decide whether a QUICK_ANSWER, DEEP_DIVE, or CODING route is required.
    - Emit a `RoutePlan` structured object with the following fields:
      - `route`: `"quick_answer"` for lightweight responses, `"deep_dive"` when external research is required, or `"coding"` when hands-on programming help is needed.
    - Prefer `"quick_answer"` when the request is straightforward, answerable from general knowledge, or when search would not add value.
    - Prefer `"deep_dive"` for questions needing up-to-date facts, citations, or multiple corroborating sources.
    - Prefer `"coding"` for programming tasks such as writing, debugging, or refactoring code where the assistant should produce or analyze code.
    - Keep the plan concise and avoid free-form commentary outside of the structured object.
    """

    router_agent = AssistantAgent(
        name="router_agent",
        model_client=quick_model,
        output_content_type=RoutePlan,
        description="Select the optimal workflow path",
        system_message=router_system_message,
    )

    research_planner_system_message = """
    You are the **research planner** for a retrieval assistant.

    - Read the conversation and craft a `ResearchPlan` structured object when a deep dive is requested.
    - Provide up to three high-quality Google search queries ordered by usefulness.
    - Set `rank_top_k` to the maximum number of search candidates that should be considered (1-5 is typical).
    - Set `fetch_page_limit` to the number of pages that should be fetched in detail (0-5, default to 3 when uncertain).
    - Stay within reasonable limits and avoid redundant or overly narrow queries.
    - Do not answer the user directly or add commentary outside of the structured object.
    """

    research_planner_agent = AssistantAgent(
        name="research_planner_agent",
        model_client=general_model,
        output_content_type=ResearchPlan,
        description="Design the deep-dive search and retrieval plan",
        system_message=research_planner_system_message,
    )

    google_search_agent = GoogleSearchExecutorAgent(
        name="google_search_agent",
        description="Run Serper searches and emit structured candidate results",
        num_results=20,
    )

    ranking_system_message = """
    You are a **search ranking analyst**.

    - Review the user's question and the `SearchCandidates` shared by the search specialist.
    - Select the strongest entries that align with the active `ResearchPlan` budget. Never exceed `rank_top_k`.
    - For each selection, provide a concise rationale in the `reason` field explaining why it is relevant.
    - Respond with a `RankedSearchResults` structured object containing a `selections` list.
    - Preserve the `title`, `url`, `snippet`, and `favicon` from the chosen candidates; do not fabricate information.
    - Do not call external tools or attempt to fetch page content.
    - Do not answer the user directly.
    """

    search_rank_agent = AssistantAgent(
        name="search_rank_agent",
        model_client=general_model,
        output_content_type=RankedSearchResults,
        description="Select the most relevant websites from the candidate list",
        system_message=ranking_system_message,
    )

    page_fetch_agent = PageFetchAgent(
        name="page_fetch_agent",
        description="Retrieve page content for ranked search selections",
        max_chars=4000,
    )

    today_date_agent = TodayDateAgent(
        name="today_date_agent",
        description="Surface the current date information for deep dive workflows",
    )

    termination = TextMentionTermination(
        "TERMINATE", sources=["report_agent", "quick_answer_agent", "coding_agent"]
    )

    report_system_message = """
    You are a helpful report-writing assistant.

    - Review the conversation, especially the fetched page content provided by the research specialist, and compose a comprehensive answer to the user.
    - Pay attention to the active `RoutePlan` to understand whether this is a quick answer or a deep dive and tailor the depth of your response accordingly.
    - Synthesize key findings, compare sources when helpful, and acknowledge any gaps or uncertainties.
    - Present the answer in clear sections or paragraphs as appropriate.
    - When you finish, append the token `TERMINATE` on a new line to signal completion.
    """

    quick_system_message = """
    You are a **rapid response assistant** trusted to deliver concise, high-quality answers.

    - Provide an accurate answer directly using your general knowledge and the conversation context.
    - If more research is required, acknowledge the limitation rather than fabricating details.
    - Keep the response focused and actionable. Include brief structure when it improves clarity.
    - When you finish, append the token `TERMINATE` on a new line to signal completion.
    """

    coding_system_message = """
    You are a **coding specialist** tasked with producing high-quality software solutions.

    - Read the conversation carefully and provide accurate, efficient code to satisfy the user's goal.
    - Offer brief explanations for non-trivial decisions and point out potential pitfalls or follow-up steps when appropriate.
    - Use Markdown code fences with language hints for all significant code snippets.
    - When you finish, append the token `TERMINATE` on a new line to signal completion.
    """

    quick_answer_agent = AssistantAgent(
        name="quick_answer_agent",
        model_client=quick_model,
        description="Deliver concise answers without external research",
        system_message=quick_system_message,
        model_client_stream=True,
    )

    coding_agent = AssistantAgent(
        name="coding_agent",
        model_client=coding_model,
        description="Provide hands-on programming assistance",
        system_message=coding_system_message,
        model_client_stream=True,
    )

    report_agent = AssistantAgent(
        name="report_agent",
        model_client=general_model,
        description="Generate a summary report based on the research findings",
        system_message=report_system_message,
        model_client_stream=True,
    )

    builder = DiGraphBuilder()
    builder.add_node(router_agent)
    builder.add_node(research_planner_agent)
    builder.add_node(google_search_agent)
    builder.add_node(search_rank_agent)
    builder.add_node(page_fetch_agent)
    builder.add_node(today_date_agent)
    builder.add_node(quick_answer_agent)
    builder.add_node(coding_agent)
    builder.add_node(report_agent)

    builder.set_entry_point(router_agent)

    builder.add_edge(
        router_agent,
        today_date_agent,
        condition=lambda msg: isinstance(msg, RoutePlanMessage)
        and msg.content.route == "deep_dive",
    )
    builder.add_edge(
        router_agent,
        research_planner_agent,
        condition=lambda msg: isinstance(msg, RoutePlanMessage)
        and msg.content.route == "deep_dive",
    )
    builder.add_edge(research_planner_agent, google_search_agent)
    builder.add_edge(google_search_agent, search_rank_agent)
    builder.add_edge(search_rank_agent, page_fetch_agent)
    builder.add_edge(page_fetch_agent, report_agent)
    builder.add_edge(
        router_agent,
        quick_answer_agent,
        condition=lambda msg: isinstance(msg, RoutePlanMessage)
        and msg.content.route == "quick_answer",
    )
    builder.add_edge(
        router_agent,
        coding_agent,
        condition=lambda msg: isinstance(msg, RoutePlanMessage)
        and msg.content.route == "coding",
    )

    graph = builder.build()

    team = GraphFlow(
        participants=builder.get_participants(),
        graph=graph,
        termination_condition=termination,
        custom_message_types=[
            RoutePlanMessage,
            ResearchPlanMessage,
            SearchQueryMessage,
            SearchCandidatesMessage,
            RankedSearchResultsMessage,
            SearchResultMessage,
            TodayDateMessage,
        ],
    )

    return team


async def ask(
    user_message: str, conversation_id: Optional[str] = None
) -> AsyncIterator[StreamMessage]:
    if not user_message or not user_message.strip():
        raise ValueError("user_message must not be empty")

    async with ConversationSession(conversation_id) as session:
        if session.conversation_id is None or session.state is None:
            return

        yield TurnStartMessage(
            type="turn.start",
            conversation_id=session.conversation_id,
        )

        planning_title = "Planning the appropriate route"
        search_step_title = "Running web search"
        coding_step_title = "Coding agent thinking"
        rank_step_title = "Ranking candidate sources"
        fetch_step_title = "Fetching supporting details"
        answer_step_title = "Answering the question"

        search_tracker = StepProgressTracker(title=search_step_title)
        processor = EventProcessor(
            planning_title=planning_title,
            search_tracker=search_tracker,
            search_prepare_description="Preparing deep dive web search queries.",
            rank_step_title=rank_step_title,
            fetch_step_title=fetch_step_title,
            coding_step_title=coding_step_title,
            answer_step_title=answer_step_title,
        )
        processor.set_planning_active(True)

        yield StepStartMessage(
            type="step.start",
            title=planning_title,
            description="Evaluating best workflow for this request.",
        )

        async for event in session.state.team.run_stream(task=user_message):
            messages = await processor.process_event(event)
            for message in messages:
                yield message
            if processor.finished:
                break


# %%
if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        question = "what is latest Line company news"
        # question = "Could you write topological sort in Python"
        print(f"Running trial ask() for: {question}")
        conversation_id: str | None = None
        async for message in ask(question):
            print(message.model_dump())
            if isinstance(message, TurnStartMessage):
                conversation_id = message.conversation_id

        # if conversation_id:
        #     follow_up = "Who did they face in the final?"
        #     print(f"\nRunning follow-up ask() for: {follow_up}")
        #     async for message in ask(follow_up, conversation_id=conversation_id):
        #         print(message.model_dump())

    asyncio.run(_demo())
