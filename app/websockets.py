"""WebSocket connection manager and Redis PubSub bridge for live job tracking."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis
import redis.asyncio as aioredis
from fastapi import WebSocket

logger = logging.getLogger(__name__)
REDIS_CHANNEL = "job_events"


class ConnectionManager:
    """Manages active WebSocket connections for live client broadcasts."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Accept incoming connection and register client."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            "WebSocket client connected. Total active: %d",
            len(self.active_connections),
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister disconnected client."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                "WebSocket client disconnected. Total active: %d",
                len(self.active_connections),
            )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast JSON payload to all active WebSocket clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


def publish_job_event(redis_url: str, event_data: dict[str, Any]) -> None:
    """Publish a live job event synchronously to Redis channel."""
    try:
        r = redis.from_url(redis_url, socket_connect_timeout=2)
        r.publish(REDIS_CHANNEL, json.dumps(event_data))
    except Exception as e:
        logger.debug("Could not publish job event to Redis: %s", e)


async def start_redis_listener(conn_manager: ConnectionManager, redis_url: str) -> None:
    """Async task subscribing to Redis PubSub and broadcasting to WebSockets."""
    while True:
        try:
            r = aioredis.from_url(
                redis_url, socket_connect_timeout=3, decode_responses=True
            )
            pubsub = r.pubsub()
            await pubsub.subscribe(REDIS_CHANNEL)
            logger.info("Subscribed to Redis channel: %s", REDIS_CHANNEL)

            async for message in pubsub.listen():
                if message and message.get("type") == "message":
                    raw_data = message.get("data")
                    if isinstance(raw_data, str):
                        try:
                            payload = json.loads(raw_data)
                            await conn_manager.broadcast(payload)
                        except Exception as e:
                            logger.error("Error parsing Redis message: %s", e)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug("Redis PubSub listener error (reconnecting): %s", e)
            await asyncio.sleep(5)
