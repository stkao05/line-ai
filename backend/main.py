import json
import logging
import os
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import StreamingResponse
from message import (
    ChatDoneEnvelope,
    ChatDonePayload,
    ChatErrorEnvelope,
    ChatErrorPayload,
    ChatStreamEnvelope,
    SseEvent,
    SseMessageAdapter,
)
from workflow import ask

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = FastAPI()

CHAT_STREAM_SCHEMA, CHAT_STREAM_DEFINITIONS = SseMessageAdapter.openapi_schema()


def custom_openapi() -> dict[str, object]:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
        description=app.description,
        summary=app.summary,
        contact=app.contact,
        license_info=app.license_info,
        terms_of_service=app.terms_of_service,
        tags=app.openapi_tags,
        servers=app.servers,
    )

    if CHAT_STREAM_DEFINITIONS:
        components = openapi_schema.setdefault("components", {})
        schemas = components.setdefault("schemas", {})
        schemas.update(CHAT_STREAM_DEFINITIONS)

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

cors_origin = os.getenv("CORS_ALLOW_ORIGIN")
if cors_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World"}


@app.get(
    "/chat",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events stream containing chat progress updates and final answer.",
            "content": {
                "text/event-stream": {
                    "schema": CHAT_STREAM_SCHEMA,
                }
            },
        }
    },
)
async def chat(
    request: Request, user_message: str, conversation_id: str | None = None
) -> StreamingResponse:
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    async def event_stream() -> AsyncIterator[str]:
        disconnected = False
        try:
            async for event in ask(user_message, conversation_id=conversation_id):
                if await request.is_disconnected():
                    disconnected = True
                    break
                envelope = ChatStreamEnvelope(event=SseEvent.MESSAGE, data=event)
                payload = json.dumps(envelope.model_dump())
                yield f"event: {envelope.event.value}\n"
                yield f"data: {payload}\n\n"
        except Exception as err:
            logger.exception("streaming /chat response failed: %s", err)
            error_envelope = ChatErrorEnvelope(
                event=SseEvent.ERROR,
                data=ChatErrorPayload(error=str(err)),
            )
            error_payload = json.dumps(error_envelope.model_dump())
            yield f"event: {error_envelope.event.value}\n"
            yield f"data: {error_payload}\n\n"

        if not disconnected:
            done_envelope = ChatDoneEnvelope(
                event=SseEvent.END,
                data=ChatDonePayload(message="[DONE]"),
            )
            done_payload = json.dumps(done_envelope.model_dump())
            yield f"event: {done_envelope.event.value}\n"
            yield f"data: {done_payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
