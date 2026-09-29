"""Minimal in-process event bus.

Modules publish domain events (e.g. "lead.created") and subscribe handlers.
The interface mirrors a message queue so handlers can be moved to Celery/
RabbitMQ consumers without changing publishers.
"""
import logging
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger("crm.events")

Handler = Callable[[dict[str, Any]], None]

_subscribers: dict[str, list[Handler]] = defaultdict(list)


def subscribe(event_name: str, handler: Handler) -> None:
    _subscribers[event_name].append(handler)


def publish(event_name: str, payload: dict[str, Any], db=None) -> None:
    """Publish an event. When `db` (the request session) is provided, in-process
    handlers join the request transaction via payload["_db"]; out-of-process
    consumers (future queue workers) simply won't receive it and open their own."""
    if db is not None:
        payload = {**payload, "_db": db}
    for handler in _subscribers.get(event_name, []):
        try:
            handler(payload)
        except Exception:  # a failing subscriber must never break the request
            logger.exception("Event handler failed for %s", event_name)
