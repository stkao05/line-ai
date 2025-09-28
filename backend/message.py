from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Snowflake = Annotated[str, Field(min_length=1)]
ISO8601 = Annotated[str, Field(min_length=1)]


class SseEvent(str, Enum):
    TURN_START = "turn.start"
    TURN_DONE = "turn.done"
    ANSWER_DELTA = "answer.delta"
    ANSWER_DONE = "answer.done"
    AGENT_STATUS = "agent.status"


class TurnStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class AgentStage(str, Enum):
    PLANNING = "planning"
    RETRIEVING = "retrieving"
    WRITING = "writing"


class BaseMeta(BaseModel):
    conversation_id: Snowflake
    turn_id: Snowflake
    id: Snowflake
    ts: ISO8601

    model_config = ConfigDict(extra="forbid")


class UserMessage(BaseModel):
    text: str

    model_config = ConfigDict(extra="forbid")


class TurnStart(BaseMeta):
    user_message: UserMessage


class TurnDone(BaseMeta):
    status: TurnStatus


class AnswerDelta(BaseMeta):
    text: str


class AnswerDone(BaseMeta):
    final_text_hash: str | None = None


class AgentStatus(BaseMeta):
    stage: AgentStage
    detail: str | None = None


class TurnStartMessage(BaseModel):
    event: Literal[SseEvent.TURN_START]
    data: TurnStart

    model_config = ConfigDict(extra="forbid")


class TurnDoneMessage(BaseModel):
    event: Literal[SseEvent.TURN_DONE]
    data: TurnDone

    model_config = ConfigDict(extra="forbid")


class AnswerDeltaMessage(BaseModel):
    event: Literal[SseEvent.ANSWER_DELTA]
    data: AnswerDelta

    model_config = ConfigDict(extra="forbid")


class AnswerDoneMessage(BaseModel):
    event: Literal[SseEvent.ANSWER_DONE]
    data: AnswerDone

    model_config = ConfigDict(extra="forbid")


class AgentStatusMessage(BaseModel):
    event: Literal[SseEvent.AGENT_STATUS]
    data: AgentStatus

    model_config = ConfigDict(extra="forbid")


SseMessage = Union[
    TurnStartMessage,
    TurnDoneMessage,
    AnswerDeltaMessage,
    AnswerDoneMessage,
    AgentStatusMessage,
]


SseMessageAdapter = TypeAdapter(SseMessage)
