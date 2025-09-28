import json
import os
from typing import AsyncIterator

from agent import ask
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

app = FastAPI()


cors_origin = os.getenv("CORS_ALLOW_ORIGIN")
print("CORS_ALLOW_ORIGIN", cors_origin)
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


@app.get("/chat")
async def chat(request: Request, question: str) -> StreamingResponse:
    if not question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    async def event_stream() -> AsyncIterator[str]:
        disconnected = False
        try:
            async for chunk in ask(question):
                if await request.is_disconnected():
                    disconnected = True
                    break
                payload = json.dumps({"message": chunk})
                yield f"data: {payload}\n\n"
        except Exception as exc:
            error_payload = json.dumps({"error": str(exc)})
            yield "event: error\n"
            yield f"data: {error_payload}\n\n"

        if not disconnected:
            done_payload = json.dumps({"message": "[DONE]"})
            yield "event: end\n"
            yield f"data: {done_payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
