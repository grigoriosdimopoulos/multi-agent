"""Chat route — submit a message, get SSE-streamed response."""
import asyncio
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..models import ChatRequest, ChatMessage
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/chat", tags=["chat"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


@router.post("/")
async def chat(body: ChatRequest, orch=Depends(get_orchestrator)):
    """
    Send a chat message to an agent.

    - If stream=true  → returns text/event-stream (SSE)
    - If stream=false → returns JSON with the full response
    """
    if not orch.agents and not orch.chains:
        raise HTTPException(503, "No agents are configured on this node")

    task_id = str(uuid.uuid4())

    if body.stream:
        return StreamingResponse(
            _stream_response(body, orch, task_id),
            media_type="text/event-stream",
            headers={"X-Task-Id": task_id},
        )

    # Non-streaming: run and return full result
    task = await orch.run_task(
        input_text=body.message,
        agent_id=body.agent_id,
        chain_id=body.chain_id,
        task_id=task_id,
    )
    await ws_manager.broadcast_task_update(task.to_dict())
    return {
        "task_id": task.task_id,
        "content": task.output,
        "status": task.status,
        "error": task.error,
    }


async def _stream_response(
    body: ChatRequest,
    orch,
    task_id: str,
) -> AsyncIterator[bytes]:
    """Yield SSE events for each token."""
    agent = None
    if body.agent_id and body.agent_id in orch.agents:
        agent = orch.agents[body.agent_id]
    elif orch.agents:
        agent = next(iter(orch.agents.values()))
    else:
        yield b"data: {\"error\": \"No agent available\"}\n\n"
        return

    yield f"data: {{\"event\": \"start\", \"task_id\": \"{task_id}\"}}\n\n".encode()

    full_response = ""
    try:
        async for token in agent.stream(body.message):
            full_response += token
            # SSE format: data: <payload>\n\n
            safe = token.replace("\n", "\\n").replace('"', '\\"')
            yield f"data: {{\"event\": \"token\", \"token\": \"{safe}\"}}\n\n".encode()
            # Also push to WebSocket clients
            await ws_manager.send_token(body.session_id, token, task_id)
    except Exception as exc:
        yield f"data: {{\"event\": \"error\", \"error\": \"{str(exc)}\"}}\n\n".encode()
        return

    yield f"data: {{\"event\": \"done\", \"task_id\": \"{task_id}\"}}\n\n".encode()

    # Record as completed task
    from datetime import datetime
    from core.orchestrator import TaskStatus
    task = TaskStatus(
        task_id=task_id,
        status="completed",
        agent_id=agent.id,
        input=body.message,
        output=full_response,
    )
    task.completed_at = datetime.utcnow()
    orch.tasks[task_id] = task
    await ws_manager.broadcast_task_update(task.to_dict())
