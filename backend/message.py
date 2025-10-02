from __future__ import annotations

from enum import Enum
from typing import Literal, Sequence, TypeAlias

from pydantic import BaseModel, TypeAdapter


class Page(BaseModel):
    """Normalized representation of a fetched page."""

    url: str
    title: str | None = None
    snippet: str | None = None
    favicon: str | None = None


class BaseStreamMessage(BaseModel):
    """Common fields shared by all streaming messages."""

    type: str

    model_config = {
        "extra": "forbid",
        "populate_by_name": True,
    }


class SearchStartMessage(BaseStreamMessage):
    type: Literal["search.start"]
    query: str


class SearchEndMessage(BaseStreamMessage):
    type: Literal["search.end"]
    query: str
    results: int


class RankStartMessage(BaseStreamMessage):
    type: Literal["rank.start"]


class RankEndMessage(BaseStreamMessage):
    type: Literal["rank.end"]
    pages: Sequence[Page]


class FetchStartMessage(BaseStreamMessage):
    type: Literal["fetch.start"]
    pages: Sequence[Page]


class FetchEndMessage(BaseStreamMessage):
    type: Literal["fetch.end"]
    pages: Sequence[Page] | None = None


class AnswerDeltaMessage(BaseStreamMessage):
    type: Literal["answer-delta"]
    delta: str


class AnswerMessage(BaseStreamMessage):
    type: Literal["answer"]
    answer: str
    citations: Sequence[Page] | None = None


StreamMessage: TypeAlias = (
    SearchStartMessage
    | SearchEndMessage
    | RankStartMessage
    | RankEndMessage
    | FetchStartMessage
    | FetchEndMessage
    | AnswerDeltaMessage
    | AnswerMessage
)

StreamMessageAdapter = TypeAdapter(StreamMessage)


class SseEvent(str, Enum):
    """Server-sent event names surfaced by the chat endpoint."""

    MESSAGE = "message"
    ERROR = "error"
    END = "end"


class ChatStreamEnvelope(BaseModel):
    """Primary chat event wrapping a streamed message payload."""

    event: Literal[SseEvent.MESSAGE]
    data: StreamMessage


class ChatErrorPayload(BaseModel):
    """Error payload sent when the stream encounters an exception."""

    error: str


class ChatErrorEnvelope(BaseModel):
    """Server-sent event dispatched when an unrecoverable error occurs."""

    event: Literal[SseEvent.ERROR]
    data: ChatErrorPayload


class ChatDonePayload(BaseModel):
    """Payload emitted when the stream has completed successfully."""

    message: Literal["[DONE]"]


class ChatDoneEnvelope(BaseModel):
    """Server-sent event dispatched when streaming is finished."""

    event: Literal[SseEvent.END]
    data: ChatDonePayload


ChatSseEvent: TypeAlias = ChatStreamEnvelope | ChatErrorEnvelope | ChatDoneEnvelope

ChatSseEventAdapter = TypeAdapter(ChatSseEvent)


class SseMessageAdapter:
    """Light-weight utilities for serialising chat SSE messages."""

    _stream_adapter = StreamMessageAdapter
    _sse_adapter = ChatSseEventAdapter

    @classmethod
    def dump_python(cls, message: StreamMessage, **kwargs) -> dict[str, object]:
        """Serialize a streamed chat message into plain Python primitives."""

        return cls._stream_adapter.dump_python(message, **kwargs)

    @classmethod
    def openapi_schema(cls) -> tuple[dict[str, object], dict[str, object]]:
        """Return the schema for chat SSE envelopes and their component models."""

        schema = cls._sse_adapter.json_schema(
            ref_template="#/components/schemas/{model}"
        )

        definitions: dict[str, object] = {}
        for key in ("definitions", "$defs"):
            maybe_defs = schema.pop(key, None)
            if maybe_defs:
                definitions = maybe_defs
                break

        return schema, definitions


__all__ = [
    "AnswerDeltaMessage",
    "AnswerMessage",
    "ChatDoneEnvelope",
    "ChatDonePayload",
    "ChatErrorEnvelope",
    "ChatErrorPayload",
    "ChatStreamEnvelope",
    "ChatSseEvent",
    "FetchEndMessage",
    "FetchStartMessage",
    "Page",
    "RankEndMessage",
    "RankStartMessage",
    "SearchEndMessage",
    "SearchStartMessage",
    "SseEvent",
    "SseMessageAdapter",
    "StreamMessage",
    "StreamMessageAdapter",
]
