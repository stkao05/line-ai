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


class TurnStartMessage(BaseStreamMessage):
    type: Literal["turn.start"]
    conversation_id: str


class StepStartMessage(BaseStreamMessage):
    type: Literal["step.start"]
    title: str
    description: str


class StepStatusMessage(BaseStreamMessage):
    type: Literal["step.status"]
    title: str
    description: str


class StepEndMessage(BaseStreamMessage):
    type: Literal["step.end"]
    title: str
    description: str | None = None


class StepFetchStartMessage(BaseStreamMessage):
    type: Literal["step.fetch.start"]
    title: str
    pages: Sequence[Page]


class StepFetchEndMessage(BaseStreamMessage):
    type: Literal["step.fetch.end"]
    title: str
    pages: Sequence[Page]


class StepAnswerStartMessage(BaseStreamMessage):
    type: Literal["step.answer.start"]
    title: str
    description: str | None = None


class StepAnswerDeltaMessage(BaseStreamMessage):
    type: Literal["step.answer.delta"]
    title: str
    delta: str


class StepAnswerEndMessage(BaseStreamMessage):
    type: Literal["step.answer.end"]
    title: str


class AnswerMessage(BaseStreamMessage):
    type: Literal["answer"]
    answer: str
    citations: Sequence[Page] | None = None


StreamMessage: TypeAlias = (
    TurnStartMessage
    | StepStartMessage
    | StepStatusMessage
    | StepEndMessage
    | StepFetchStartMessage
    | StepFetchEndMessage
    | StepAnswerStartMessage
    | StepAnswerDeltaMessage
    | StepAnswerEndMessage
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
    "AnswerMessage",
    "ChatDoneEnvelope",
    "ChatDonePayload",
    "ChatErrorEnvelope",
    "ChatErrorPayload",
    "ChatStreamEnvelope",
    "ChatSseEvent",
    "TurnStartMessage",
    "Page",
    "StepAnswerEndMessage",
    "StepAnswerDeltaMessage",
    "StepAnswerStartMessage",
    "StepEndMessage",
    "StepFetchEndMessage",
    "StepFetchStartMessage",
    "StepStartMessage",
    "StepStatusMessage",
    "SseEvent",
    "SseMessageAdapter",
    "StreamMessage",
    "StreamMessageAdapter",
]
