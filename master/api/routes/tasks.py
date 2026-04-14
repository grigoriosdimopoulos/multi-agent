"""
Task routes — submit tasks to worker nodes via Redis, track results.

Master never executes tasks locally. It:
  1. Generates a task_id and stores a pending record in app.state.task_registry
  2. Publishes the task payload to Redis (tasks:{node_id} or tasks:broadcast)
  3. Returns the pending TaskResponse immediately (202 Accepted)

Results come back asynchronously via the Redis "results" channel subscriber
in main.py, which updates task_registry and broadcasts to WebSocket clients.
"""
import json
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request

from ..models import TaskCreateRequest, TaskResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])

NODE_SHARED_SECRET = os.getenv("NODE_SHARED_SECRET", "")


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _make_task_record(task_id: str, body: TaskCreateRequest) -> dict:
    return {
        "task_id": task_id,
        "status": "pending",
        "agent_id": body.agent_id,
        "chain_id": body.chain_id,
        "node_id": body.node_id,
        "input": body.input,
        "output": None,
        "error": None,
        "created_at": _now_iso(),
        "completed_at": None,
        "iterations": 0,
        "subtask_ids": [],
        "required_tools": body.required_tools,
        "privilege_level": body.privilege_level,
    }


def _record_to_response(r: dict) -> TaskResponse:
    return TaskResponse(**{k: r.get(k) for k in TaskResponse.model_fields})


# -----------------------------------------------------------------------
# List / Get
# -----------------------------------------------------------------------

@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    request: Request,
    status: Optional[str] = None,
):
    registry: dict = request.app.state.task_registry
    tasks = list(registry.values())
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    # Newest first
    tasks.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return [_record_to_response(t) for t in tasks]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, request: Request):
    registry: dict = request.app.state.task_registry
    task = registry.get(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return _record_to_response(task)


# -----------------------------------------------------------------------
# Submit
# -----------------------------------------------------------------------

@router.post("/", response_model=TaskResponse, status_code=202)
async def submit_task(body: TaskCreateRequest, request: Request):
    registry: dict = request.app.state.task_registry
    redis = request.app.state.redis

    task_id = str(uuid.uuid4())
    record = _make_task_record(task_id, body)
    registry[task_id] = record

    # Build Redis payload — includes everything the node needs
    payload = {
        "task_id": task_id,
        "input": body.input,
        "agent_id": body.agent_id,
        "chain_id": body.chain_id,
        "recursive": body.recursive,
        "required_tools": body.required_tools,
        "privilege_level": body.privilege_level,
        "prerequisites": body.prerequisites,
        "chain_config": body.chain_config,
        "node_secret": NODE_SHARED_SECRET,
    }

    # Route to specific node or broadcast
    channel = f"tasks:{body.node_id}" if body.node_id else "tasks:broadcast"
    try:
        await redis.publish(channel, json.dumps(payload))
        logger.info("Task %s dispatched to channel '%s'", task_id, channel)
    except Exception as exc:
        logger.error("Failed to publish task %s: %s", task_id, exc)
        record["status"] = "failed"
        record["error"] = f"Redis dispatch error: {exc}"

    return _record_to_response(record)


# -----------------------------------------------------------------------
# Cancel (best-effort: marks as cancelled in registry; node may still run)
# -----------------------------------------------------------------------

@router.delete("/{task_id}", status_code=204)
async def cancel_task(task_id: str, request: Request):
    registry: dict = request.app.state.task_registry
    task = registry.get(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    if task["status"] in ("pending", "running"):
        task["status"] = "cancelled"
        task["completed_at"] = _now_iso()
