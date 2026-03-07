from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import datetime, timezone

import uvloop
from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import get_settings
from database.mongo import MongoEngine
from database.redis_engine import RedisEngine
from handlers.chat_proxy import router as chat_router
from handlers.inline_match import router as match_router
from handlers.registration import router as registration_router
from handlers.twa_swipe import router as swipe_router
from middlewares.auth import RegistrationRequiredMiddleware
from middlewares.throttling import ThrottlingMiddleware
from services.ai_matcher import AIMatcherService
from services.elo_rating import EloService


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())


def build_system_router(bot_username: str) -> Router:
    router = Router(name='system')

    @router.message(Command('refer'))
    async def refer(message: Message) -> None:
        link = f'https://t.me/{bot_username}?start=ref_{message.from_user.id}'
        await message.answer(f'Invite and earn reveal tokens + VIP queue:\n{link}')

    return router


async def send_daily_secret_admirer(bot: Bot, mongo: MongoEngine) -> None:
    cursor = mongo.db.users.find({'intent': {'$in': ['dating', 'marriage']}}, projection={'user_id': 1})
    users = await cursor.to_list(length=1000)
    for user in users:
        with suppress(Exception):
            await bot.send_message(
                user['user_id'],
                '💌 Secret Admirer: Someone in the 18-22 bracket liked your profile. Invite 1 friend to reveal who it is!',
            )


async def update_chat_streaks(mongo: MongoEngine) -> None:
    today = datetime.now(timezone.utc).date().isoformat()
    await mongo.db.users.update_many(
        {'last_seen_date': {'$ne': today}},
        {'$set': {'last_seen_date': today}, '$inc': {'streak_days': 1}},
    )


async def on_startup(bot: Bot, mongo: MongoEngine, scheduler: AsyncIOScheduler, settings) -> None:
    await mongo.ensure_indexes()
    await bot.set_webhook(
        url=f'{settings.resolved_webhook_base_url}{settings.webhook_path}',
        secret_token=settings.webhook_secret,
    )
    await bot.set_my_commands(
        [
            BotCommand(command='start', description='Create your profile'),
            BotCommand(command='match', description='Find anonymous chat partner'),
            BotCommand(command='marry', description='Open swipe mode'),
            BotCommand(command='reveal', description='Mutual reveal request'),
            BotCommand(command='next', description='End current chat'),
            BotCommand(command='refer', description='Get referral link'),
        ]
    )
    scheduler.start()


async def on_shutdown(bot: Bot, redis_engine: RedisEngine, mongo: MongoEngine, scheduler: AsyncIOScheduler) -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

    sessions = await redis_engine.redis.keys('session:*')
    for key in sessions:
        payload = await redis_engine.redis.get(key)
        if payload:
            await mongo.db.chat_logs.insert_one(
                {'session_key': key, 'payload': payload, 'status': 'interrupted_restart', 'created_at': datetime.now(timezone.utc)}
            )

    await bot.delete_webhook(drop_pending_updates=True)
    await redis_engine.close()
    await mongo.close()


def build_dispatcher(mongo: MongoEngine, redis_engine: RedisEngine, settings, bot_username: str) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    matcher = AIMatcherService(settings)
    elo = EloService()

    dp.update.middleware(RegistrationRequiredMiddleware(mongo))
    dp.message.middleware(ThrottlingMiddleware(redis_engine, settings))

    dp['mongo'] = mongo
    dp['redis_engine'] = redis_engine
    dp['matcher'] = matcher
    dp['settings'] = settings
    dp['elo_service'] = elo

    dp.include_router(build_system_router(bot_username))
    dp.include_router(registration_router)
    dp.include_router(match_router)
    dp.include_router(swipe_router)
    dp.include_router(chat_router)
    return dp


async def health(_: web.Request) -> web.Response:
    return web.json_response({'ok': True})


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()

    mongo = MongoEngine(settings)
    redis_engine = RedisEngine(settings)
    scheduler = AsyncIOScheduler(timezone='UTC')

    scheduler.add_job(send_daily_secret_admirer, 'cron', hour=9, kwargs={'bot': bot, 'mongo': mongo})
    scheduler.add_job(update_chat_streaks, 'cron', hour=0, minute=5, kwargs={'mongo': mongo})

    dp = build_dispatcher(mongo, redis_engine, settings, me.username)
    dp.startup.register(lambda b: on_startup(b, mongo, scheduler, settings))
    dp.shutdown.register(lambda b: on_shutdown(b, redis_engine, mongo, scheduler))

    app = web.Application()
    app.router.add_get('/healthz', health)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.webhook_host, port=settings.webhook_port)
    await site.start()

    while True:
        await asyncio.sleep(3600)


if __name__ == '__main__':
    asyncio.run(main())
