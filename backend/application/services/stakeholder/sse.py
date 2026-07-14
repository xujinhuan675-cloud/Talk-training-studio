# input: asyncio.Queue
# output: RoomEventBus 有界 SSE 事件总线
# owner: wanhua.gu
# pos: 应用层 - 聊天室 SSE 事件发布/订阅总线；一旦我被更新，务必更新我的开头注释以及所属文件夹的md
"""SSE event bus for stakeholder chat rooms.

Each room has a set of bounded subscriber queues. When an event is published,
it is pushed to all active subscribers for that room. If a subscriber falls
behind, the bus keeps the freshest event instead of accumulating an unbounded
backlog.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

RoomEventEnvelope = tuple[str, Any]


class RoomEventBus:
    """In-memory pub/sub for SSE events, keyed by room_id."""

    def __init__(self, subscriber_queue_size: int = 64) -> None:
        if subscriber_queue_size < 1:
            raise ValueError("subscriber_queue_size must be at least 1")
        self._subscriber_queue_size = subscriber_queue_size
        self._subscribers: dict[int, set[asyncio.Queue[RoomEventEnvelope]]] = {}

    def subscribe(self, room_id: int) -> asyncio.Queue[RoomEventEnvelope]:
        """Create a new subscriber queue for a room."""
        queue: asyncio.Queue[RoomEventEnvelope] = asyncio.Queue(
            maxsize=self._subscriber_queue_size
        )
        self._subscribers.setdefault(room_id, set()).add(queue)
        return queue

    def unsubscribe(self, room_id: int, queue: asyncio.Queue[RoomEventEnvelope]) -> None:
        """Remove a subscriber queue."""
        subscribers = self._subscribers.get(room_id)
        if not subscribers:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(room_id, None)

    async def publish(self, room_id: int, event: str, data: Any) -> None:
        """Push an event to all subscribers of a room."""
        envelope: RoomEventEnvelope = (event, data)
        for queue in list(self._subscribers.get(room_id, [])):
            self._enqueue_latest(queue, envelope)

    @staticmethod
    def _enqueue_latest(
        queue: asyncio.Queue[RoomEventEnvelope], envelope: RoomEventEnvelope
    ) -> None:
        while queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        queue.put_nowait(envelope)


def format_sse(event: str, data: Any) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# Singleton event bus
room_event_bus = RoomEventBus()
