"""Chat route — submit a message, get SSE-streamed response with full tool use."""
import json
import re
import uuid
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..models import ChatRequest, ChatMessage
from ..websocket_manager import ws_manager
from core.orchestrator import TaskStatus

router = APIRouter(prefix="/chat", tags=["chat"])

# Patterns that indicate a knowledge-base lookup vs a file/greeting
_GREETING_RE = re.compile(
    r"^\s*(hi|hello|hey|γεια|γεια\s*σου|καλημέρα|καλησπέρα|what can you do|τι μπορείς)\b",
    re.IGNORECASE,
)
_FILE_ACTION_RE = re.compile(
    r"\b(list|read|write|open|show\s+files|ls|delete|create\s+file|fetch|http)"
    r"|(/Users/|~/|\.\.?/|\\)",
    re.IGNORECASE,
)


def _should_auto_search_kb(message: str) -> bool:
    """Heuristic: anything that isn't a greeting or explicit file operation
    is likely a question the knowledge base might answer."""
    if _GREETING_RE.search(message):
        return False
    if _FILE_ACTION_RE.search(message):
        return False
    return True


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


def _sse_event(payload: dict) -> bytes:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n".encode("utf-8")


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
            headers={
                "X-Task-Id": task_id,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

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
    """
    Run the agent's full ReAct loop (with tools) and stream progress as SSE.

    Auto-searches the knowledge base for question-like messages before handing
    off to the LLM so the model always has relevant context.
    """
    agent = None
    if body.agent_id and body.agent_id in orch.agents:
        agent = orch.agents[body.agent_id]
    elif orch.agents:
        agent = next(iter(orch.agents.values()))
    else:
        yield _sse_event({"event": "error", "error": "No agent available"})
        return

    agent.reset_memory()

    yield _sse_event({"event": "start", "task_id": task_id})

    # --- Auto-inject KB context for question-like messages ----------------
    kb_context = ""
    if _should_auto_search_kb(body.message):
        kb_tool = agent._tool_map.get("query_knowledge_base")
        if kb_tool:
            try:
                yield _sse_event({
                    "event": "thinking",
                    "tool": "query_knowledge_base",
                    "arguments": {"query": body.message},
                })
                kb_result = await kb_tool.execute(query=body.message)
                if kb_result.success and kb_result.output:
                    chunks = kb_result.output
                    if isinstance(chunks, list) and chunks:
                        parts = []
                        for c in chunks[:5]:
                            text = c.get("content", "") if isinstance(c, dict) else str(c)
                            score = c.get("score", 0) if isinstance(c, dict) else 0
                            if score > -0.1:
                                parts.append(text[:500])
                        if parts:
                            kb_context = (
                                "\n\n--- KNOWLEDGE BASE RESULTS ---\n"
                                + "\n---\n".join(parts)
                                + "\n--- END OF KB RESULTS ---\n"
                            )
            except Exception:
                pass

    try:
        enriched_message = body.message
        if kb_context:
            enriched_message = (
                body.message
                + "\n\n[The following was automatically retrieved from the knowledge base. "
                "Use it to answer the question. If the results are not relevant, say so.]\n"
                + kb_context
            )

        result = await agent.run(enriched_message)

        if not result.success and result.error:
            yield _sse_event({"event": "error", "error": result.error})
            return

        if result.tool_calls:
            for tc in result.tool_calls:
                yield _sse_event({
                    "event": "thinking",
                    "tool": tc["name"],
                    "arguments": tc.get("arguments", {}),
                })

        content = result.content or "(empty reply)"
        yield _sse_event({"event": "token", "token": content})

    except Exception as exc:
        yield _sse_event({"event": "error", "error": str(exc)})
        return

    yield _sse_event({"event": "done", "task_id": task_id})

    task = TaskStatus(
        task_id=task_id,
        status="completed",
        agent_id=agent.id,
        input=body.message,
        output=content,
    )
    task.completed_at = datetime.utcnow()
    orch.tasks[task_id] = task
    await ws_manager.broadcast_task_update(task.to_dict())
