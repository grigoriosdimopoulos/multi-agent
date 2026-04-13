"""
WebSocket connection manager — handles all real-time browser connections.

Events pushed to clients:
  token          streaming LLM token
  task_update    task status change
  notification   system notification (node connected, error, …)
  agent_update   agent created / deleted
"""
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe (asyncio) WebSocket pool."""

    def __init__(self) -> None:
        # session_id → WebSocket
        self._connections: dict[str, WebSocket] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, websocket: WebSocket, session_id: str) -> None:
        await websocket.accept()
        self._connections[session_id] = websocket
        logger.info("WS connected: %s  (total: %d)", session_id, len(self._connections))

    def disconnect(self, session_id: str) -> None:
        self._connections.pop(session_id, None)
        logger.info("WS disconnected: %s", session_id)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send(self, session_id: str, data: dict) -> None:
        ws = self._connections.get(session_id)
        if ws:
            try:
                await ws.send_json(data)
            except Exception as exc:
                logger.warning("Send failed for %s: %s", session_id, exc)
                self.disconnect(session_id)

    async def broadcast(self, data: dict) -> None:
        dead: list[str] = []
        for sid, ws in list(self._connections.items()):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(sid)
        for sid in dead:
            self.disconnect(sid)

    # ------------------------------------------------------------------
    # Typed helpers
    # ------------------------------------------------------------------

    async def send_token(self, session_id: str, token: str, task_id: str) -> None:
        await self.send(session_id, {"type": "token", "task_id": task_id, "token": token})

    async def broadcast_task_update(self, task: dict) -> None:
        await self.broadcast({"type": "task_update", "data": task})

    async def broadcast_notification(self, notification: dict) -> None:
        await self.broadcast({"type": "notification", "data": notification})

    async def broadcast_agent_update(self, agent: dict, action: str = "updated") -> None:
        await self.broadcast({"type": "agent_update", "action": action, "data": agent})

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def count(self) -> int:
        return len(self._connections)

    def session_ids(self) -> list[str]:
        return list(self._connections.keys())


# Module-level singleton
ws_manager = ConnectionManager()
