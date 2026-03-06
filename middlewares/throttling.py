from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message

from config import Settings
from database.redis_engine import RedisEngine


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, redis_engine: RedisEngine, settings: Settings) -> None:
        self.redis_engine = redis_engine
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        if not event.from_user:
            return await handler(event, data)
        allowed = await self.redis_engine.set_throttle(event.from_user.id, self.settings.throttle_seconds)
        if not allowed:
            return await event.answer('⏱️ Easy there — max 1 message/second to keep chats smooth.')
        return await handler(event, data)
