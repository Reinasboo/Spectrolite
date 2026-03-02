"""
Redis Signal Bus — centralised pub/sub data backbone.

Instead of each worker independently polling DexScreener / Birdeye / Pump.fun,
one SignalPublisher fetches data and fans it out via Redis channels.
Workers subscribe via SignalSubscriber and never make raw API calls.

Eliminates 2/3 of external API calls at full 3-worker scale.

Channels:
  chain:solana          VolumeAnomaly dicts for Solana tokens
  chain:base            ''  for Base
  chain:bnb             ''  for BNB Chain
  chain:ethereum        ''  for Ethereum
  sentiment:<symbol>    SentimentResult dicts keyed by token symbol
  pumpfun:launch        New Pump.fun token launches (raw event dicts)
  arb:opportunity       ArbOpportunity dicts from CrossChainArbDetector
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "spectrolite:"


class SignalPublisher:
    """
    Runs in a single dedicated process / worker.
    Fetches all raw data and publishes to Redis channels.
    All other workers subscribe instead of fetching.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis  # type: ignore
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def publish(self, channel: str, payload: dict[str, Any]) -> None:
        """Publish a single payload to a Redis channel."""
        client = await self._get_client()
        full_channel = f"{_CHANNEL_PREFIX}{channel}"
        try:
            await client.publish(full_channel, json.dumps(payload, default=str))
        except Exception as exc:
            logger.warning(f"SignalBus publish failed on {channel}: {exc}")

    async def publish_many(self, channel: str, payloads: list[dict[str, Any]]) -> None:
        """Batch publish. Uses a pipeline for efficiency."""
        if not payloads:
            return
        client = await self._get_client()
        full_channel = f"{_CHANNEL_PREFIX}{channel}"
        pipe = client.pipeline()
        for p in payloads:
            pipe.publish(full_channel, json.dumps(p, default=str))
        try:
            await pipe.execute()
        except Exception as exc:
            logger.warning(f"SignalBus batch publish failed on {channel}: {exc}")

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()


class SignalSubscriber:
    """
    Workers subscribe to specific channels and receive signal dicts
    without ever calling external APIs directly.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self._redis_url = redis_url
        self._pubsub: Any = None
        self._client: Any = None

    async def _get_pubsub(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis  # type: ignore
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
            self._pubsub = self._client.pubsub()
        return self._pubsub

    async def subscribe(self, *channels: str) -> None:
        """Subscribe to one or more channels."""
        ps = await self._get_pubsub()
        full = [f"{_CHANNEL_PREFIX}{c}" for c in channels]
        await ps.subscribe(*full)
        logger.info(f"SignalSubscriber subscribed to: {full}")

    async def subscribe_pattern(self, pattern: str) -> None:
        """Subscribe to a channel pattern, e.g. 'chain:*'."""
        ps = await self._get_pubsub()
        await ps.psubscribe(f"{_CHANNEL_PREFIX}{pattern}")

    async def listen(self) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """
        Async generator yielding (channel_name, payload_dict) for each message.
        Strip the _CHANNEL_PREFIX from channel before yielding.
        """
        ps = await self._get_pubsub()
        async for message in ps.listen():
            if message["type"] not in ("message", "pmessage"):
                continue
            raw_channel: str = message.get("channel") or message.get("pattern") or ""
            channel = raw_channel.removeprefix(_CHANNEL_PREFIX)
            try:
                payload = json.loads(message["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            yield channel, payload

    async def close(self) -> None:
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.aclose()
        if self._client:
            await self._client.aclose()


class SignalBusRouter:
    """
    Dispatches incoming signals from a subscriber to registered handler callbacks.

    Usage:
        router = SignalBusRouter(subscriber)
        router.on("chain:solana", handle_solana_signal)
        router.on("pumpfun:launch", handle_new_launch)
        await router.run()
    """

    def __init__(self, subscriber: SignalSubscriber) -> None:
        self._sub = subscriber
        self._handlers: dict[str, list[Callable]] = {}

    def on(self, channel: str, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Register a handler for a channel (or channel prefix)."""
        self._handlers.setdefault(channel, []).append(handler)

    async def run(self) -> None:
        """Start routing messages. Blocks until cancelled."""
        logger.info("SignalBusRouter: running…")
        async for channel, payload in self._sub.listen():
            handlers = self._handlers.get(channel, [])
            # Also match prefix handlers (e.g. 'chain:*')
            for key, hlist in self._handlers.items():
                if key.endswith("*") and channel.startswith(key[:-1]):
                    handlers = handlers + hlist
            for handler in handlers:
                try:
                    result = handler(payload)
                    if asyncio.iscoroutine(result):
                        asyncio.create_task(result)
                except Exception as exc:
                    logger.warning(f"SignalBus handler error on {channel}: {exc}")
