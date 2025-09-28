import json
import logging
import os
from typing import AsyncIterator

from agent import ask
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from message import SseEvent, SseMessageAdapter

logging.basicConfig(level=logging.WARNING)

app = FastAPI()

logger = logging.getLogger(__name__)


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


@app.get("/chat/event-type")
async def chat_type() -> dict[str, list[str]]:
    return {"events": [event.value for event in SseEvent]}


@app.get("/chat")
async def chat(request: Request, user_message: str) -> StreamingResponse:
    if not user_message.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    async def event_stream() -> AsyncIterator[str]:
        disconnected = False
        try:
            async for event in ask(user_message):
                if await request.is_disconnected():
                    disconnected = True
                    break
                payload_dict = SseMessageAdapter.dump_python(event, mode="json")
                payload = json.dumps(payload_dict)
                yield f"data: {payload}\n\n"
        except Exception as err:
            logger.exception("streaming /chat response failed: %s", err)
            # TODO: design better message
            error_payload = json.dumps({"error": str(err)})
            yield "event: error\n"
            yield f"data: {error_payload}\n\n"

        if not disconnected:
            done_payload = json.dumps({"message": "[DONE]"})
            yield "event: end\n"
            yield f"data: {done_payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
