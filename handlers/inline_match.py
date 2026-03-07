from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from config import Settings
from database.mongo import MongoEngine
from database.redis_engine import RedisEngine
from services.elo_rating import EloService

router = Router(name='inline_match')


def age_bucket(age: int) -> str:
    if age <= 22:
        return '18-22'
    if age <= 30:
        return '23-30'
    return '31-80'


async def _queue_timeout_notify(message: Message, redis_engine: RedisEngine, delay_seconds: int) -> None:
    await asyncio.sleep(delay_seconds)
    pending = await redis_engine.redis.get(f'pending:{message.from_user.id}')
    if pending:
        await redis_engine.clear_pending_queue(message.from_user.id)
        await message.answer('No instant match yet 😇 Try again in a moment or tweak your profile intent.')


@router.message(Command('match'))
async def find_match(
    message: Message,
    mongo: MongoEngine,
    redis_engine: RedisEngine,
    settings: Settings,
    elo_service: EloService,
) -> None:
    user_id = message.from_user.id
    if await redis_engine.get_session(user_id):
        await message.answer('You are already in a live anonymous chat. Use /next to find a new match.')
        return

    me = await mongo.get_user(user_id)
    if not me:
        await message.answer('Please register first with /start')
        return

    bucket = age_bucket(me['age'])
    elo_tier = elo_service.tier(me.get('elo', 1000))
    queue = redis_engine.queue_key(me['intent'], me.get('looking_for', 'any'), bucket, elo_tier)

    # O(1) queue matching: pop from head; if candidate unavailable, keep popping until a valid partner appears.
    partner = None
    while True:
        raw = await redis_engine.pop_queue(queue)
        if not raw:
            break
        candidate_id = int(raw)
        if candidate_id == user_id:
            continue
        if await mongo.are_blocked(user_id, candidate_id):
            continue
        candidate_session = await redis_engine.get_session(candidate_id)
        if candidate_session:
            continue
        partner = candidate_id
        break

    if partner:
        session_id = await redis_engine.set_session(user_id, partner, settings.chat_session_ttl_seconds)
        await redis_engine.clear_pending_queue(user_id)
        await message.answer('🎯 Match found! You are now chatting anonymously. Use /reveal, /report, /block, /next')
        await message.bot.send_message(partner, '🎯 Match found! Anonymous chat started. Use /reveal when ready.')
        await mongo.log_chat(session_id, user_id, partner, 'session_started', status='system')
        return

    await redis_engine.push_queue(queue, user_id)
    await redis_engine.set_pending_queue(user_id, queue, settings.queue_ttl_seconds)
    asyncio.create_task(_queue_timeout_notify(message, redis_engine, settings.queue_ttl_seconds))
    await message.answer('Searching in ultra-fast queue... ⏳ (up to 3 minutes)')
