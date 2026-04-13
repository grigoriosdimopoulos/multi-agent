"""Task submit / query routes."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ..models import TaskCreateRequest, TaskResponse
from ..websocket_manager import ws_manager

router = APIRouter(prefix="/tasks", tags=["tasks"])


def get_orchestrator(request: Request):
    return request.app.state.orchestrator


def _task_to_response(task) -> TaskResponse:
    return TaskResponse(
        task_id=task.task_id,
        status=task.status,
        agent_id=task.agent_id,
        chain_id=task.chain_id,
        input=task.input,
        output=task.output,
        error=task.error,
        created_at=task.created_at,
        completed_at=task.completed_at,
        iterations=task.iterations,
        subtask_ids=task.subtask_ids,
    )


@router.get("/", response_model=list[TaskResponse])
async def list_tasks(
    status: Optional[str] = None,
    orch=Depends(get_orchestrator),
):
    return [_task_to_response(t) for t in orch.list_tasks(status=status)]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str, orch=Depends(get_orchestrator)):
    task = orch.get_task(task_id)
    if not task:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return _task_to_response(task)


@router.post("/", response_model=TaskResponse, status_code=202)
async def submit_task(body: TaskCreateRequest, orch=Depends(get_orchestrator)):
    import asyncio

    # Fire-and-forget: run the task in the background
    async def _run():
        task = await orch.run_task(
            input_text=body.input,
            agent_id=body.agent_id,
            chain_id=body.chain_id,
            recursive=body.recursive,
        )
        await ws_manager.broadcast_task_update(task.to_dict())

    asyncio.create_task(_run())

    # Return a placeholder immediately
    from datetime import datetime
    import uuid
    from core.orchestrator import TaskStatus
    placeholder = TaskStatus(
        task_id=str(uuid.uuid4()),
        status="pending",
        agent_id=body.agent_id,
        chain_id=body.chain_id,
        input=body.input,
        recursive=body.recursive,
    )
    orch.tasks[placeholder.task_id] = placeholder
    return _task_to_response(placeholder)
