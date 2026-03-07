from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import Message

from database.mongo import MongoEngine
from database.redis_engine import RedisEngine
from services.ai_matcher import AIMatcherService
from services.elo_rating import EloService

router = Router(name='chat_proxy')


@router.message(Command('next'))
async def next_chat(message: Message, redis_engine: RedisEngine) -> None:
    session = await redis_engine.get_session(message.from_user.id)
    if not session:
        await message.answer('No active chat. Use /match')
        return
    partner_id = int(session['partner_id'])
    await redis_engine.end_session(message.from_user.id, partner_id)
    await message.answer('Ended chat. Use /match for another match.')
    await message.bot.send_message(partner_id, 'Your partner left the chat. Use /match for new match.')


@router.message(Command('reveal'))
async def reveal_identity(message: Message, redis_engine: RedisEngine, mongo: MongoEngine, elo: EloService) -> None:
    user_id = message.from_user.id
    session = await redis_engine.get_session(user_id)
    if not session:
        await message.answer('You are not in chat.')
        return

    partner_id = int(session['partner_id'])
    await redis_engine.set_reveal(user_id)
    if not await redis_engine.has_reveal(partner_id):
        await message.answer('Reveal request sent. Waiting for your partner consent.')
        await message.bot.send_message(partner_id, 'Your partner requested /reveal. Send /reveal to accept.')
        return

    me = await mongo.get_user(user_id)
    partner = await mongo.get_user(partner_id)
    if not me or not partner:
        await message.answer('Profile missing for reveal.')
        return

    await message.answer(f"🤝 Mutual reveal! Name: {partner.get('nickname')} | Age: {partner.get('age')}")
    await message.bot.send_message(partner_id, f"🤝 Mutual reveal! Name: {me.get('nickname')} | Age: {me.get('age')}")

    await mongo.db.users.update_one({'user_id': user_id}, {'$set': {'elo': elo.update_on_mutual_reveal(me.get('elo', 1000))}})
    await mongo.db.users.update_one({'user_id': partner_id}, {'$set': {'elo': elo.update_on_mutual_reveal(partner.get('elo', 1000))}})


@router.message(Command('report'))
async def report_user(message: Message, redis_engine: RedisEngine, mongo: MongoEngine) -> None:
    session = await redis_engine.get_session(message.from_user.id)
    if not session:
        await message.answer('No active chat to report.')
        return
    partner_id = int(session['partner_id'])
    await mongo.add_block_pair(message.from_user.id, partner_id, reason='report')
    await redis_engine.end_session(message.from_user.id, partner_id)
    await message.answer('User reported and blocked from future matching.')


@router.message(Command('block'))
async def block_user(message: Message, redis_engine: RedisEngine, mongo: MongoEngine) -> None:
    session = await redis_engine.get_session(message.from_user.id)
    if not session:
        await message.answer('No active chat to block.')
        return
    partner_id = int(session['partner_id'])
    await mongo.add_block_pair(message.from_user.id, partner_id, reason='manual_block')
    await redis_engine.end_session(message.from_user.id, partner_id)
    await message.answer('User blocked. You will not be matched again.')


@router.message(F.text)
async def proxy_message(
    message: Message,
    redis_engine: RedisEngine,
    mongo: MongoEngine,
    matcher: AIMatcherService,
    elo_service: EloService,
) -> None:
    text = message.text or ''
    if text.startswith('/'):
        return

    session = await redis_engine.get_session(message.from_user.id)
    if not session:
        return

    partner_id = int(session['partner_id'])
    toxic, score, reason = await matcher.moderation_check(text)
    me = await mongo.get_user(message.from_user.id)
    me_elo = (me or {}).get('elo', 1000)

    if toxic:
        new_elo = elo_service.update_on_toxicity(me_elo, score)
        await mongo.db.users.update_one({'user_id': message.from_user.id}, {'$set': {'elo': new_elo}})
        await mongo.log_chat(session['session_id'], message.from_user.id, partner_id, text, status='blocked_toxic')
        await message.answer(f'⚠️ Message blocked by AI moderation ({reason}). Keep it respectful.')
        return

    try:
        await message.bot.send_message(partner_id, f'👤 Stranger: {text}')
        await mongo.log_chat(session['session_id'], message.from_user.id, partner_id, text)
    except (TelegramForbiddenError, TelegramBadRequest):
        await redis_engine.end_session(message.from_user.id, partner_id)
        await message.answer('Partner disconnected. Session ended.')

    # Example quick-skip ELO update hook (for metrics if clients trigger /next early).
    started_at = int(session['session_id'].split(':')[-1])
    duration = int(datetime.now(timezone.utc).timestamp()) - started_at
    if duration < 30 and 'bye' in text.lower():
        downgraded = elo_service.update_on_quick_skip(me_elo, duration)
        await mongo.db.users.update_one({'user_id': message.from_user.id}, {'$set': {'elo': downgraded}})
