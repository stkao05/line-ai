# %%
import hashlib
import json
import os
from datetime import datetime, timezone
from typing import AsyncIterator, List, Optional
from uuid import uuid4

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.messages import (
    BaseTextChatMessage,
    ModelClientStreamingChunkEvent,
    StructuredMessage,
    TextMessage,
    ToolCallRequestEvent,
)
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core.tools import FunctionTool
from autogen_ext.models.openai import OpenAIChatCompletionClient
from message import (
    AgentStage,
    AgentStatus,
    AgentStatusMessage,
    AnswerDelta,
    AnswerDeltaMessage,
    AnswerDone,
    AnswerDoneMessage,
    SseEvent,
    SseMessage,
    TurnDone,
    TurnDoneMessage,
    TurnStart,
    TurnStartMessage,
    TurnStatus,
    UserMessage,
)
from pydantic import BaseModel
from tools import google_search

openai_api_key = os.getenv("OPENAI_API_KEY")
model_client = OpenAIChatCompletionClient(model="gpt-4o", api_key=openai_api_key)


class SearchResultItem(BaseModel):
    title: str
    url: str
    favicon: Optional[str] = None
    snippet: str
    detail_summary: str


class SearchResult(BaseModel):
    results: List[SearchResultItem]


SearchResultMessage = StructuredMessage[SearchResult]


google_search_tool = FunctionTool(
    google_search,
    description="Search Google for information",
    strict=True,
)


def create_team():
    search_system_message = """
    You are a **search assistant agent**.  

    - Given a user’s question, generate **one or more precise Google search queries** that are most likely to retrieve high-quality answers.  
    - Use the **Google search tool** to fetch up to **5 candidate pages**.  
    - From those, select the **top 3 most relevant results**.  
    - For each result, return a structured object with the following fields:  
    - `title`: page title  
    - `url`: canonical page URL  
    - `favicon`: site favicon (if available)  
    - `snippet`: a short extract showing relevance  
    - `detail_summary`: a clear, well-organized summary of the page content that contains all necessary details to answer the user’s question. The summary should be comprehensive, but focused on the user’s query.  
    - Ensure results are **ranked by relevance**, not just by order of retrieval.
    """

    search_agent = AssistantAgent(
        name="google_search_agent",
        model_client=model_client,
        tools=[google_search_tool],
        output_content_type=SearchResult,
        description="Search Google for relevant information that could help answering the question",
        system_message=search_system_message,
    )

    termination = TextMentionTermination("TERMINATE", sources=["report_agent"])
    report_agent = AssistantAgent(
        name="report_agent",
        model_client=model_client,
        description="Generate a summary report based on the search result",
        system_message="You are a helpful assistant that can generate a comprehensive report on a given topic based on search. When you done with generating the report, reply with TERMINATE.",
        model_client_stream=True,
    )

    team = RoundRobinGroupChat(
        [search_agent, report_agent],
        custom_message_types=[SearchResultMessage],
        termination_condition=termination,
    )

    return team


async def ask(
    user_message: str, conversation_id: Optional[str] = None
) -> AsyncIterator[SseMessage]:
    """Stream SSE messages that mirror the frontend types."""

    conversation_id = conversation_id or uuid4().hex
    turn_id = uuid4().hex
    final_chunks: List[str] = []
    final_text: Optional[str] = None
    writing_announced = False
    status = TurnStatus.OK

    def iso_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def next_event_id() -> str:
        return uuid4().hex

    def make_turn_start() -> TurnStartMessage:
        return TurnStartMessage(
            event=SseEvent.TURN_START,
            data=TurnStart(
                conversation_id=conversation_id,
                turn_id=turn_id,
                id=next_event_id(),
                ts=iso_now(),
                user_message=UserMessage(text=user_message),
            ),
        )

    def make_turn_done(turn_status: TurnStatus) -> TurnDoneMessage:
        return TurnDoneMessage(
            event=SseEvent.TURN_DONE,
            data=TurnDone(
                conversation_id=conversation_id,
                turn_id=turn_id,
                id=next_event_id(),
                ts=iso_now(),
                status=turn_status,
            ),
        )

    def make_answer_delta(delta_text: str) -> AnswerDeltaMessage:
        return AnswerDeltaMessage(
            event=SseEvent.ANSWER_DELTA,
            data=AnswerDelta(
                conversation_id=conversation_id,
                turn_id=turn_id,
                id=next_event_id(),
                ts=iso_now(),
                text=delta_text,
            ),
        )

    def make_answer_done(final_answer: str) -> AnswerDoneMessage:
        final_hash = hashlib.sha256(final_answer.encode("utf-8")).hexdigest()
        return AnswerDoneMessage(
            event=SseEvent.ANSWER_DONE,
            data=AnswerDone(
                conversation_id=conversation_id,
                turn_id=turn_id,
                id=next_event_id(),
                ts=iso_now(),
                final_text_hash=final_hash,
            ),
        )

    def make_agent_status(
        stage: AgentStage, detail: Optional[str] = None
    ) -> AgentStatusMessage:
        return AgentStatusMessage(
            event=SseEvent.AGENT_STATUS,
            data=AgentStatus(
                conversation_id=conversation_id,
                turn_id=turn_id,
                id=next_event_id(),
                ts=iso_now(),
                stage=stage,
                detail=detail,
            ),
        )

    def coerce_tool_arguments(arguments) -> dict:
        if isinstance(arguments, dict):
            return arguments
        if isinstance(arguments, str):
            try:
                parsed = json.loads(arguments)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {"query": arguments}
            return {}
        return {}

    yield make_turn_start()
    yield make_agent_status(AgentStage.PLANNING)

    team = create_team()
    stream = team.run_stream(task=user_message)

    try:
        async for msg in stream:
            if (
                isinstance(msg, ToolCallRequestEvent)
                and msg.source == "google_search_agent"
                and msg.content
            ):
                arguments = getattr(msg.content[0], "arguments", {})
                parsed_args = coerce_tool_arguments(arguments)
                query_text = parsed_args.get("query")
                if not query_text:
                    queries = parsed_args.get("queries")
                    if isinstance(queries, list) and queries:
                        query_text = queries[0]
                if isinstance(query_text, list) and query_text:
                    query_text = query_text[0]
                if not isinstance(query_text, str):
                    query_text = user_message

                yield make_agent_status(
                    AgentStage.RETRIEVING,
                    detail=f"searching: {query_text}",
                )
                continue

            if (
                isinstance(msg, StructuredMessage)
                and msg.source == "google_search_agent"
                and isinstance(msg.content, SearchResult)
            ):
                count = len(msg.content.results)
                detail = f"retrieved {count} result{'s' if count != 1 else ''}"
                yield make_agent_status(AgentStage.PLANNING, detail=detail)
                continue

            if isinstance(msg, ModelClientStreamingChunkEvent):
                chunk_content = msg.content
                if isinstance(chunk_content, BaseTextChatMessage):
                    chunk_text = getattr(chunk_content, "text", None) or getattr(
                        chunk_content, "content", ""
                    )
                elif isinstance(chunk_content, dict):
                    chunk_text = chunk_content.get("delta") or json.dumps(chunk_content)
                else:
                    chunk_text = str(chunk_content)

                if not chunk_text:
                    continue

                final_chunks.append(chunk_text)
                if not writing_announced:
                    yield make_agent_status(AgentStage.WRITING)
                    writing_announced = True

                yield make_answer_delta(chunk_text)
                continue

            if isinstance(msg, TextMessage) and msg.source == "report_agent":
                text_content = msg.content.strip()
                if not text_content:
                    continue
                if text_content.upper() == "TERMINATE":
                    continue
                if text_content.endswith("TERMINATE"):
                    text_content = text_content[: -len("TERMINATE")].strip()
                if text_content:
                    final_text = text_content
                    if not final_chunks:
                        if not writing_announced:
                            yield make_agent_status(AgentStage.WRITING)
                            writing_announced = True
                        final_chunks.append(text_content)
                        yield make_answer_delta(text_content)

    except Exception as exc:  # pragma: no cover - defensive guard
        status = TurnStatus.ERROR
        yield make_agent_status(AgentStage.WRITING, detail=str(exc))

    combined_text = final_text or "".join(final_chunks).strip()
    if combined_text and status == TurnStatus.OK:
        yield make_answer_done(combined_text)

    yield make_turn_done(status)


# %%
# import asyncio

# stream = ask("give me a short history of chatgpt")
# messages = []
# async for message in stream:
#     messages.append(message)


# %%

# messages


# %%

# from rich import inspect, pretty
# from rich import print as pprint

# pprint(messages[3])


# # %%

# %%
