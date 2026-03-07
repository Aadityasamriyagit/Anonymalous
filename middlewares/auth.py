from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, Update

from database.mongo import MongoEngine


class RegistrationRequiredMiddleware(BaseMiddleware):
    def __init__(self, mongo: MongoEngine) -> None:
        self.mongo = mongo

    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        message: Message | None = getattr(event, 'message', None)
        if not message or not message.from_user:
            return await handler(event, data)

        text = message.text or ''
        if text.startswith('/start'):
            return await handler(event, data)

        user = await self.mongo.get_user(message.from_user.id)
        if not user:
            return await message.answer('Please complete onboarding first via /start')
        return await handler(event, data)
