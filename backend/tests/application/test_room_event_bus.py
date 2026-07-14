"""Focused tests for the stakeholder room event bus."""

from __future__ import annotations

import asyncio

import pytest

from application.services.stakeholder.sse import RoomEventBus


@pytest.mark.asyncio
async def test_room_event_bus_publish_and_subscribe() -> None:
    bus = RoomEventBus()
    queue = bus.subscribe(1)

    await asyncio.wait_for(
        bus.publish(1, "message", {"content": "hello"}), timeout=1
    )

    assert await asyncio.wait_for(queue.get(), timeout=1) == (
        "message",
        {"content": "hello"},
    )

    bus.unsubscribe(1, queue)


@pytest.mark.asyncio
async def test_room_event_bus_unsubscribe_stops_delivery() -> None:
    bus = RoomEventBus()
    queue = bus.subscribe(1)

    await asyncio.wait_for(bus.publish(1, "message", {"sequence": 1}), timeout=1)
    assert await asyncio.wait_for(queue.get(), timeout=1) == (
        "message",
        {"sequence": 1},
    )

    bus.unsubscribe(1, queue)

    await asyncio.wait_for(bus.publish(1, "message", {"sequence": 2}), timeout=1)
    assert queue.empty()


@pytest.mark.asyncio
async def test_room_event_bus_drops_oldest_when_queue_is_full() -> None:
    bus = RoomEventBus(subscriber_queue_size=1)
    queue = bus.subscribe(1)

    await asyncio.wait_for(bus.publish(1, "message", {"sequence": 1}), timeout=1)
    await asyncio.wait_for(bus.publish(1, "message", {"sequence": 2}), timeout=1)

    assert queue.qsize() == 1
    assert await asyncio.wait_for(queue.get(), timeout=1) == (
        "message",
        {"sequence": 2},
    )

    bus.unsubscribe(1, queue)
