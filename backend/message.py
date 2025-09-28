from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class LinkPreview(BaseModel):
    id: Optional[str] = None
    title: str
    url: str
    snippet: Optional[str] = None
    favicon_url: Optional[str] = None


# ---------------------------
# Envelope base (abstract)
# ---------------------------


class EventBase(BaseModel):
    """Common envelope for all events."""

    type: str  # overridden by Literal[...] in concrete subclasses
    request_id: str
    seq: int
    ts: datetime


# ---------------------------
# Payload models
# ---------------------------


class EmptyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchStartedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    fetch: int = Field(ge=1, description="Number of results to fetch")


class SearchResultsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results: List[LinkPreview]


class AnswerDeltaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta: str


class AnswerFinalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    citations: Optional[List[LinkPreview]] = None


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    retryable: Optional[bool] = None


class CompletePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["success", "error", "cancelled"]
    usage: Optional[dict] = Field(
        default=None,
        description="Optional usage stats, e.g. {'input_tokens': 123, 'output_tokens': 456}",
    )
    latency_ms: Optional[int] = None


# ---------------------------
# Concrete event models
# ---------------------------


class InitEvent(EventBase):
    type: Literal["init"]
    payload: EmptyPayload = Field(default_factory=EmptyPayload)


class SearchStartedEvent(EventBase):
    type: Literal["search.started"]
    payload: SearchStartedPayload


class SearchResultsEvent(EventBase):
    type: Literal["search.results"]
    payload: SearchResultsPayload


class AnswerDeltaEvent(EventBase):
    type: Literal["answer.delta"]
    payload: AnswerDeltaPayload


class AnswerFinalEvent(EventBase):
    type: Literal["answer.final"]
    payload: AnswerFinalPayload


class ErrorEvent(EventBase):
    type: Literal["error"]
    payload: ErrorPayload


class CompleteEvent(EventBase):
    type: Literal["complete"]
    payload: CompletePayload


# ---------------------------
# Discriminated union
# ---------------------------

StreamEvent = Annotated[
    Union[
        InitEvent,
        SearchStartedEvent,
        SearchResultsEvent,
        AnswerDeltaEvent,
        AnswerFinalEvent,
        ErrorEvent,
        CompleteEvent,
    ],
    Field(discriminator="type"),
]

# A TypeAdapter is convenient for (de)serializing top-level unions:
StreamEventAdapter = TypeAdapter(StreamEvent)


# ---------------------------
# Request model (for POST /v1/qa/stream)
# ---------------------------


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    fetch: int = Field(default=5, ge=1)


# ---------------------------
# Helpers
# ---------------------------


def parse_ndjson_line(line: str) -> StreamEvent:
    """Validate and parse a single NDJSON line into a concrete event model."""
    return StreamEventAdapter.validate_json(line)


def dump_event(event: StreamEvent) -> str:
    """Serialize an event to a JSON string (ready to send as an NDJSON line)."""
    return StreamEventAdapter.dump_json(event)
