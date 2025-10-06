from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator, Dict, List, Optional, Set
from uuid import uuid4

from agent import (
    RankedSearchResultsMessage,
    ResearchPlan,
    ResearchPlanMessage,
    RoutePlanMessage,
    SearchCandidatesMessage,
    SearchResultMessage,
    create_team,
)
from autogen_agentchat.base import TaskResult
from autogen_agentchat.messages import (
    BaseTextChatMessage,
    ModelClientStreamingChunkEvent,
    StructuredMessage,
)
from autogen_agentchat.teams import GraphFlow
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
from pydantic import ValidationError


@dataclass
class ConversationState:
    team: GraphFlow
    lock: asyncio.Lock
    last_used: datetime


_conversation_states: Dict[str, ConversationState] = {}
CONVERSATION_TTL = timedelta(days=1)


def _purge_expired_conversations(now: datetime) -> None:
    expiration_threshold = now - CONVERSATION_TTL
    expired_conv_ids: List[str] = []
    for conv_id, state in list(_conversation_states.items()):
        if state.lock.locked():
            continue
        if state.last_used < expiration_threshold:
            expired_conv_ids.append(conv_id)

    for conv_id in expired_conv_ids:
        _conversation_states.pop(conv_id, None)


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
        now = datetime.now(timezone.utc)
        _purge_expired_conversations(now)
        conv_id = self._requested_id or uuid4().hex
        state = _conversation_states.get(conv_id)
        if state is None:
            state = ConversationState(
                team=create_team(), lock=asyncio.Lock(), last_used=now
            )
            _conversation_states[conv_id] = state
        else:
            state.last_used = now

        if state.lock.locked():
            raise RuntimeError(
                f"conversation '{conv_id}' is already processing another request"
            )

        await state.lock.acquire()
        state.last_used = now
        self.conversation_id = conv_id
        self.state = state
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.state is not None:
            self.state.last_used = datetime.now(timezone.utc)
            self.state.lock.release()


class EventProcessor:
    """Dispatch agent events to dedicated handlers for streaming output."""

    def __init__(self, stream: AsyncIterator[object], conversation_id: str) -> None:
        self._planning_step_open = False
        self._search_step_open = False

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
        self._stream = stream
        self._conversation_id = conversation_id

    def set_planning_active(self, active: bool) -> None:
        self._planning_step_open = active

    async def run(self) -> AsyncIterator[StreamMessage]:
        yield TurnStartMessage(
            type="turn.start",
            conversation_id=self._conversation_id,
        )

        self.set_planning_active(True)

        yield StepStartMessage(
            type="step.start",
            title="Planning the appropriate route",
            description="Evaluating best workflow for this request.",
        )

        async for event in self._stream:
            messages = await self.process_event(event)
            for message in messages:
                yield message
            if self.finished:
                break

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
                        title="Coding agent thinking",
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
                self._open_search_step("Preparing deep dive web search queries.")
            )

        if self._planning_step_open:
            messages.append(
                StepEndMessage(
                    type="step.end",
                    title="Planning the appropriate route",
                    description=end_description,
                )
            )
            self._planning_step_open = False

        return messages

    def handle_ResearchPlanMessage(
        self, event: ResearchPlanMessage
    ) -> List[StreamMessage]:
        self._active_research_plan = event.content

        query = event.content.queries[0]  # TODO: for simplicity only search one
        messages: List[StreamMessage] = []
        messages.extend(self._open_search_step(f'Searching for "{query}".'))
        messages.append(
            StepStatusMessage(
                type="step.status",
                title="Running web search",
                description=f'Searching with "{query}".',
            )
        )
        return messages

    def handle_SearchCandidatesMessage(
        self, event: SearchCandidatesMessage
    ) -> List[StreamMessage]:
        candidate_count = len(event.content.candidates)
        messages: List[StreamMessage] = []
        messages.extend(self._close_search_step(f"Found {candidate_count} candidates."))
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
                    title="Ranking candidate sources",
                    description=f"Selected {len(ranked_pages)} pages for deeper research.",
                )
            )
            self._rank_step_completed = True

        if fetch_start_pages:
            messages.append(
                StepFetchStartMessage(
                    type="step.fetch.start",
                    title="Fetching supporting details",
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
                title="Fetching supporting details",
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
                    title="Coding agent thinking",
                    description="Coding approach finalized – composing response.",
                )
            )
            self._coding_step_open = False

        messages.extend(self._ensure_answer_step_started())
        self._answer_chunks.append(content)
        messages.append(
            StepAnswerDeltaMessage(
                type="step.answer.delta",
                title="Answering the question",
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
                    title="Coding agent thinking",
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
                    title="Answering the question",
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

    def _open_search_step(self, description: str) -> List[StreamMessage]:
        if self._search_step_open:
            return []

        self._search_step_open = True
        return [
            StepStartMessage(
                type="step.start",
                title="Running web search",
                description=description,
            )
        ]

    def _close_search_step(self, description: str) -> List[StreamMessage]:
        if not self._search_step_open:
            return []

        self._search_step_open = False
        return [
            StepEndMessage(
                type="step.end",
                title="Running web search",
                description=description,
            )
        ]

    def _ensure_answer_step_started(self) -> List[StreamMessage]:
        if self._answer_step_started:
            return []

        self._answer_step_started = True
        return [
            StepAnswerStartMessage(
                type="step.answer.start",
                title="Answering the question",
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
                title="Ranking candidate sources",
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


async def ask(
    user_message: str, conversation_id: Optional[str] = None
) -> AsyncIterator[StreamMessage]:
    if not user_message or not user_message.strip():
        raise ValueError("user_message must not be empty")

    async with ConversationSession(conversation_id) as session:
        if session.conversation_id is None or session.state is None:
            return

        stream = session.state.team.run_stream(task=user_message)
        processor = EventProcessor(stream, session.conversation_id)

        async for message in processor.run():
            yield message


# for manual testing
if __name__ == "__main__":
    import asyncio

    async def _demo() -> None:
        question = "what is latest Line company news"
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
