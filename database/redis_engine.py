from __future__ import annotations

import json
from datetime import datetime, timezone

import redis.asyncio as redis

from config import Settings


class RedisEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis = redis.from_url(settings.redis_url, decode_responses=True)

    @staticmethod
    def queue_key(intent: str, looking_for: str, age_bucket: str, elo_tier: str) -> str:
        return f'queue:{intent}:{looking_for}:{age_bucket}:{elo_tier}'

    async def push_queue(self, key: str, user_id: int) -> None:
        await self.redis.rpush(key, user_id)

    async def pop_queue(self, key: str) -> str | None:
        return await self.redis.lpop(key)

    async def set_pending_queue(self, user_id: int, key: str, ttl: int) -> None:
        await self.redis.setex(f'pending:{user_id}', ttl, key)

    async def clear_pending_queue(self, user_id: int) -> None:
        await self.redis.delete(f'pending:{user_id}')

    async def set_session(self, user_a: int, user_b: int, ttl: int) -> str:
        session_id = f'{min(user_a, user_b)}:{max(user_a, user_b)}:{int(datetime.now(timezone.utc).timestamp())}'
        pipe = self.redis.pipeline()
        pipe.setex(f'session:{user_a}', ttl, json.dumps({'partner_id': user_b, 'session_id': session_id}))
        pipe.setex(f'session:{user_b}', ttl, json.dumps({'partner_id': user_a, 'session_id': session_id}))
        pipe.sadd('active_sessions', session_id)
        await pipe.execute()
        return session_id

    async def get_session(self, user_id: int) -> dict | None:
        raw = await self.redis.get(f'session:{user_id}')
        return json.loads(raw) if raw else None

    async def end_session(self, user_id: int, partner_id: int | None = None) -> None:
        if partner_id is None:
            session = await self.get_session(user_id)
            partner_id = session.get('partner_id') if session else None
        pipe = self.redis.pipeline()
        pipe.delete(f'session:{user_id}')
        if partner_id:
            pipe.delete(f'session:{partner_id}')
        pipe.delete(f'reveal:{user_id}')
        if partner_id:
            pipe.delete(f'reveal:{partner_id}')
        await pipe.execute()

    async def set_reveal(self, user_id: int, ttl: int = 1800) -> None:
        await self.redis.setex(f'reveal:{user_id}', ttl, '1')

    async def has_reveal(self, user_id: int) -> bool:
        return bool(await self.redis.get(f'reveal:{user_id}'))

    async def set_throttle(self, user_id: int, ttl: int) -> bool:
        # SET key value EX ttl NX is O(1) in Redis and perfect for one-request-per-window controls.
        ok = await self.redis.set(f'throttle:{user_id}', '1', ex=ttl, nx=True)
        return bool(ok)

    async def close(self) -> None:
        await self.redis.aclose()
