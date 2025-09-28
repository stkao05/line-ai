import json
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from agent import ask


app = FastAPI()


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
