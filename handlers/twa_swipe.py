from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import Settings
from database.mongo import MongoEngine
from services.ai_matcher import AIMatcherService

router = Router(name='twa_swipe')


def _swipe_keyboard(target_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text='❌ Skip', callback_data=f'swipe:skip:{target_id}'),
        InlineKeyboardButton(text='❤️ Like', callback_data=f'swipe:like:{target_id}'),
        InlineKeyboardButton(text='🌟 Super Like', callback_data=f'swipe:superlike:{target_id}'),
    )
    return builder.as_markup()


@router.message(Command('marry'))
async def start_swipe(message: Message, mongo: MongoEngine, matcher: AIMatcherService) -> None:
    me = await mongo.get_user(message.from_user.id)
    if not me:
        await message.answer('Use /start first.')
        return

    cursor = mongo.db.users.find(
        {
            'user_id': {'$ne': message.from_user.id},
            'intent': {'$in': ['dating', 'marriage']},
        },
        limit=30,
    )
    pool = await cursor.to_list(length=30)
    ranked = await matcher.best_candidates(me.get('bio_embedding', []), pool, top_k=1)
    if not ranked:
        await message.answer('No profiles found now. Try later.')
        return

    candidate = ranked[0]
    caption = (
        f"{candidate.get('nickname')} | {candidate.get('age')}\n"
        f"Intent: {candidate.get('intent')}\n"
        f"Compatibility: {candidate.get('compatibility_score')}%"
    )
    await message.answer(caption, reply_markup=_swipe_keyboard(candidate['user_id']))


@router.callback_query(F.data.startswith('swipe:'))
async def handle_swipe(callback, mongo: MongoEngine, settings: Settings) -> None:
    _, action, target_raw = callback.data.split(':', maxsplit=2)
    target_id = int(target_raw)
    user_id = callback.from_user.id

    if action == 'superlike':
        me = await mongo.get_user(user_id)
        if (me or {}).get('reveal_tokens', 0) < settings.superlike_token_cost:
            await callback.answer('Not enough premium tokens for superlike.', show_alert=True)
            return
        await mongo.db.users.update_one({'user_id': user_id}, {'$inc': {'reveal_tokens': -settings.superlike_token_cost}})

    await mongo.add_swipe(user_id, target_id, action)
    mutual = action in {'like', 'superlike'} and await mongo.has_mutual_like(user_id, target_id)

    if mutual:
        await callback.message.answer('💘 Mutual match! Starting anonymous chat channel. Use /match now.')
        await callback.bot.send_message(target_id, '💘 Mutual like! Open /match and you will be prioritized together.')
    else:
        await callback.answer('Recorded!')
