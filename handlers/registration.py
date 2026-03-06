from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from database.mongo import MongoEngine
from services.ai_matcher import AIMatcherService

router = Router(name='registration')


class RegistrationFSM(StatesGroup):
    nickname = State()
    gender = State()
    age = State()
    intent = State()
    bio = State()


def _gender_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text='M'), KeyboardButton(text='F'), KeyboardButton(text='Other')]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _intent_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text='Just Chat'), KeyboardButton(text='Dating')],
            [KeyboardButton(text='Marriage'), KeyboardButton(text='Fun')],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


@router.message(CommandStart())
async def start_registration(message: Message, state: FSMContext) -> None:
    payload = message.text.split(maxsplit=1)
    if len(payload) > 1:
        await state.update_data(start_payload=payload[1])
    await state.set_state(RegistrationFSM.nickname)
    await message.answer('Welcome to Anonymalous Match 🚀\nChoose a nickname:')


@router.message(RegistrationFSM.nickname)
async def set_nickname(message: Message, state: FSMContext) -> None:
    await state.update_data(nickname=message.text.strip())
    await state.set_state(RegistrationFSM.gender)
    await message.answer('Gender?', reply_markup=_gender_keyboard())


@router.message(RegistrationFSM.gender, F.text.in_({'M', 'F', 'Other'}))
async def set_gender(message: Message, state: FSMContext) -> None:
    await state.update_data(gender=message.text)
    await state.set_state(RegistrationFSM.age)
    await message.answer('Age (number only):')


@router.message(RegistrationFSM.age)
async def set_age(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit() or not (18 <= int(message.text) <= 80):
        await message.answer('Please enter a valid age 18-80.')
        return
    await state.update_data(age=int(message.text))
    await state.set_state(RegistrationFSM.intent)
    await message.answer('Intent?', reply_markup=_intent_keyboard())


@router.message(RegistrationFSM.intent, F.text.in_({'Just Chat', 'Dating', 'Marriage', 'Fun'}))
async def set_intent(message: Message, state: FSMContext) -> None:
    await state.update_data(intent=message.text.lower().replace(' ', '_'))
    await state.set_state(RegistrationFSM.bio)
    await message.answer('Write a short bio so AI can find your best matches.')


@router.message(RegistrationFSM.bio)
async def set_bio(
    message: Message,
    state: FSMContext,
    mongo: MongoEngine,
    matcher: AIMatcherService,
) -> None:
    form = await state.get_data()
    bio = (message.text or '').strip()
    embedding = await matcher.embed_bio(bio)

    referral_payload = form.get('start_payload', '')
    referred_by = None
    if referral_payload.startswith('ref_'):
        try:
            referred_by = int(referral_payload.replace('ref_', ''))
        except ValueError:
            referred_by = None

    await mongo.upsert_user(
        message.from_user.id,
        {
            'user_id': message.from_user.id,
            'nickname': form['nickname'],
            'gender': form['gender'],
            'age': form['age'],
            'intent': form['intent'],
            'bio': bio,
            'bio_embedding': embedding,
            'looking_for': 'any',
        },
    )
    if referred_by and referred_by != message.from_user.id:
        await mongo.set_referral(message.from_user.id, referred_by)

    await state.clear()
    await message.answer('✅ Profile created. Use /match for anonymous chat or /marry for swipe mode.')

