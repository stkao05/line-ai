from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import os
import sys

import pytest

os.environ.setdefault("SERPER_API_KEY", "test-key")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent as backend_agent  # type: ignore  # noqa: E402
from message import (  # type: ignore  # noqa: E402
    AnswerMessage,
    StepAnswerDeltaMessage,
    StepAnswerEndMessage,
    StepAnswerStartMessage,
    StepEndMessage,
    StepStartMessage,
    StepStatusMessage,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio("asyncio")
async def test_conversation_session_reuses_state(monkeypatch: pytest.MonkeyPatch) -> None:
    backend_agent._conversation_states.clear()
    sentinel_team = object()

    monkeypatch.setattr(backend_agent, "create_team", lambda: sentinel_team)

    async with backend_agent.ConversationSession(None) as session_one:
        assert session_one.conversation_id is not None
        assert session_one.state is not None
        assert session_one.state.team is sentinel_team
        conversation_id = session_one.conversation_id
        state_ref = session_one.state

    async with backend_agent.ConversationSession(conversation_id) as session_two:
        assert session_two.conversation_id == conversation_id
        assert session_two.state is state_ref

    backend_agent._conversation_states.clear()


def test_step_progress_tracker_transitions() -> None:
    tracker = backend_agent.StepProgressTracker(title="Search")

    start_messages = tracker.start_step("Starting search")
    assert len(start_messages) == 1
    assert isinstance(start_messages[0], StepStartMessage)

    # Repeated starts should not emit new messages while the step is open.
    assert tracker.start_step("Starting search again") == []

    assert tracker.record_query("widgets") is True
    assert tracker.record_query("widgets") is False

    status_messages = tracker.emit_status("widgets", "Searching for widgets")
    assert len(status_messages) == 1
    assert isinstance(status_messages[0], StepStatusMessage)

    # Duplicated status updates are suppressed.
    assert tracker.emit_status("widgets", "Searching for widgets") == []

    completion_messages = tracker.complete_step(
        "widgets", "Finished searching for widgets"
    )
    assert len(completion_messages) == 1
    assert isinstance(completion_messages[0], StepEndMessage)

    # Completing again should not re-emit end events.
    assert (
        tracker.complete_step("widgets", "Finished searching for widgets") == []
    )


@pytest.mark.anyio("asyncio")
async def test_event_processor_streaming_flow() -> None:
    class RoutePlanMessage:
        def __init__(self, route: str) -> None:
            self.content = SimpleNamespace(route=route)

    class ModelClientStreamingChunkEvent:
        def __init__(self, source: str, content: str) -> None:
            self.source = source
            self.content = content

    class TaskResult:
        def __init__(self) -> None:
            self.messages: list[object] = []

    tracker = backend_agent.StepProgressTracker(title="Search")
    processor = backend_agent.EventProcessor(
        planning_title="Plan",
        search_tracker=tracker,
        search_prepare_description="Prepare search",
        rank_step_title="Rank",
        fetch_step_title="Fetch",
        coding_step_title="Code",
        answer_step_title="Answer",
    )
    processor.set_planning_active(True)

    route_messages = await processor.process_event(RoutePlanMessage("quick_answer"))
    assert any(isinstance(message, StepEndMessage) for message in route_messages)
    assert processor.finished is False

    chunk_messages = await processor.process_event(
        ModelClientStreamingChunkEvent("quick_answer_agent", "Hello")
    )
    assert any(
        isinstance(message, StepAnswerStartMessage) for message in chunk_messages
    )
    deltas = [
        message
        for message in chunk_messages
        if isinstance(message, StepAnswerDeltaMessage)
    ]
    assert len(deltas) == 1 and deltas[0].delta == "Hello"

    final_messages = await processor.process_event(TaskResult())
    assert any(
        isinstance(message, StepAnswerEndMessage) for message in final_messages
    )
    answers = [
        message for message in final_messages if isinstance(message, AnswerMessage)
    ]
    assert answers and answers[0].answer == "Hello"
    assert processor.finished is True


@pytest.mark.anyio("asyncio")
async def test_ask_streams_quick_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class RoutePlanMessage:
        def __init__(self, route: str) -> None:
            self.content = SimpleNamespace(route=route)

    class ModelClientStreamingChunkEvent:
        def __init__(self, source: str, content: str) -> None:
            self.source = source
            self.content = content

    class TaskResult:
        def __init__(self) -> None:
            self.messages: list[object] = []

    events = [
        RoutePlanMessage("quick_answer"),
        ModelClientStreamingChunkEvent("quick_answer_agent", "Hello "),
        ModelClientStreamingChunkEvent("quick_answer_agent", "world TERMINATE"),
        TaskResult(),
    ]

    class DummyTeam:
        def __init__(self, stream_events: list[object]) -> None:
            self._events = list(stream_events)

        async def run_stream(self, task: str):  # pragma: no cover - async generator
            for event in self._events:
                yield event

    class DummyConversationSession:
        def __init__(self, *_: object) -> None:
            self.conversation_id = "dummy-conv"
            self.state = SimpleNamespace(team=DummyTeam(events))

        async def __aenter__(self) -> "DummyConversationSession":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(backend_agent, "ConversationSession", DummyConversationSession)

    streamed: list[AnswerMessage | StepStartMessage | StepEndMessage | StepAnswerStartMessage | StepAnswerDeltaMessage | StepAnswerEndMessage] = []
    async for message in backend_agent.ask("hello"):
        streamed.append(message)

    message_types = [message.type for message in streamed]
    assert message_types == [
        "turn.start",
        "step.start",
        "step.end",
        "step.answer.start",
        "step.answer.delta",
        "step.answer.delta",
        "step.answer.end",
        "answer",
    ]

    answer_start = streamed[3]
    assert isinstance(answer_start, StepAnswerStartMessage)
    assert (
        answer_start.description
        == "Drafting a direct reply without additional research."
    )

    answer_message = streamed[-1]
    assert isinstance(answer_message, AnswerMessage)
    assert answer_message.answer == "Hello world"
