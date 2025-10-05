from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Sequence

from autogen_agentchat.agents import AssistantAgent, BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.messages import BaseChatMessage, StructuredMessage
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient
from pydantic import BaseModel
from tools import fetch_page, google_search

openai_api_key = os.getenv("OPENAI_API_KEY")
general_model = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_api_key)
quick_model = OpenAIChatCompletionClient(model="gpt-4o-mini", api_key=openai_api_key)
coding_model = OpenAIChatCompletionClient(model="gpt-5", api_key=openai_api_key)


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
        plan_message = _latest_message_of_type(messages, ResearchPlanMessage)

        query_text = ""
        if isinstance(plan_message, ResearchPlanMessage):
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

    # deep dive branch
    builder.add_edge(
        router_agent,
        today_date_agent,
        condition=lambda msg: isinstance(msg, RoutePlanMessage)
        and msg.content.route == "deep_dive",
    )
    builder.add_edge(
        today_date_agent,
        research_planner_agent,
    )
    builder.add_edge(research_planner_agent, google_search_agent)
    builder.add_edge(google_search_agent, search_rank_agent)
    builder.add_edge(search_rank_agent, page_fetch_agent)
    builder.add_edge(page_fetch_agent, report_agent)

    # quick answer branch
    builder.add_edge(
        router_agent,
        quick_answer_agent,
        condition=lambda msg: isinstance(msg, RoutePlanMessage)
        and msg.content.route == "quick_answer",
    )

    # coding branch
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
            SearchCandidatesMessage,
            RankedSearchResultsMessage,
            SearchResultMessage,
            TodayDateMessage,
        ],
    )

    return team
