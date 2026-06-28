from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any

from .jsonl_store import JsonlStore
from .service_contracts import utc_now


class EventBus:
    def __init__(self, store_path: Path | None = None):
        self._events: list[dict[str, Any]] = []
        self._lock = Lock()
        self._store = JsonlStore(store_path) if store_path else None

    def publish(self, event_type: str, payload: dict[str, Any], *, source: str) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "source": source,
            "timestamp": utc_now(),
            "payload": payload,
        }
        with self._lock:
            self._events.append(event)
            if len(self._events) > 1000:
                self._events = self._events[-1000:]
        if self._store:
            self._store.append(event)
        return event

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        if self._store:
            return self._store.tail(limit)
        with self._lock:
            return list(self._events[-max(1, limit) :])