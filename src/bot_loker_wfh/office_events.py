"""Thread-safe, bounded pub/sub for live office activity events."""
from __future__ import annotations

import queue
import threading
import time
from typing import Any


class EventSubscription:
    def __init__(self, bus: "EventBus", maxsize: int) -> None:
        self._bus = bus
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=maxsize)
        self.closed = False

    def get(self, timeout: float | None = None) -> dict[str, Any]:
        return self.queue.get(timeout=timeout)

    def close(self) -> None:
        self._bus.unsubscribe(self)


class EventBus:
    def __init__(self, maxsize: int = 100) -> None:
        self.maxsize = maxsize
        self._lock = threading.Lock()
        self._subscribers: set[EventSubscription] = set()

    def subscribe(self, maxsize: int | None = None) -> EventSubscription:
        subscription = EventSubscription(self, maxsize or self.maxsize)
        with self._lock:
            self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: EventSubscription) -> None:
        with self._lock:
            subscription.closed = True
            self._subscribers.discard(subscription)

    def publish(self, event: dict[str, Any]) -> None:
        # Caller supplies already-safe structured fields; copy prevents mutation races.
        item = dict(event)
        item.setdefault("timestamp", time.time())
        with self._lock:
            subscribers = tuple(self._subscribers)
        for subscription in subscribers:
            if subscription.closed:
                continue
            try:
                subscription.queue.put_nowait(item.copy())
            except queue.Full:
                try:
                    subscription.queue.get_nowait()
                except queue.Empty:
                    pass
                try:
                    subscription.queue.put_nowait(item.copy())
                except queue.Full:
                    pass


bus = EventBus()

__all__ = ["EventBus", "EventSubscription", "bus"]
