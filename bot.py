import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGODB_URI")

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client.anonymalous
users = db.users
chats = db.chats
referrals = db.referrals

# Inline keyboards
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Match Someone", callback_data="match")],
        [InlineKeyboardButton(text="🎭 Random Chat", callback_data="random")],
        [InlineKeyboardButton(text="📣 Refer & Earn", callback_data="refer")]
    ])

@dp.message(F.text == "/start")
async def start(message: Message):
    user = await users.find_one({"id": message.from_user.id})
    if not user:
        await users.insert_one({"id": message.from_user.id, "step": "name"})
        await message.answer("👋 Welcome to Anonymalous!
What is your name?")
    else:
        await message.answer("Welcome back! Use the menu below.", reply_markup=main_menu())

@dp.message()
async def collect_info(message: Message):
    user = await users.find_one({"id": message.from_user.id})
    if not user or "step" not in user: return

    step = user["step"]
    val = message.text.strip()

    if step == "name":
        await users.update_one({"id": message.from_user.id}, {"$set": {"name": val, "step": "age"}})
        await message.answer("📅 What's your exact age?")
    elif step == "age":
        if not val.isdigit():
            await message.answer("Please enter a valid number.")
            return
        await users.update_one({"id": message.from_user.id}, {"$set": {"age": int(val), "step": "gender"}})
        await message.answer("🚻 Your gender? (Male/Female)")
    elif step == "gender":
        if val.lower() not in ["male", "female"]:
            await message.answer("Type 'Male' or 'Female'")
            return
        await users.update_one({"id": message.from_user.id}, {"$set": {"gender": val.lower(), "step": "preference"}})
        await message.answer("💘 Interested in? (Male/Female/Anyone)")
    elif step == "preference":
        if val.lower() not in ["male", "female", "anyone"]:
            await message.answer("Type Male, Female, or Anyone")
            return
        await users.update_one({"id": message.from_user.id}, {"$set": {"preference": val.lower(), "step": "done"}})
        await message.answer("🎉 Profile setup complete!", reply_markup=main_menu())

@dp.callback_query(F.data == "match")
async def match_user(callback):
    user = await users.find_one({"id": callback.from_user.id})
    if not user or user.get("step") != "done":
        await callback.message.answer("Please complete your profile using /start.")
        return
    gender = user["gender"]
    pref = user["preference"]

    query = {"id": {"$ne": user["id"]}, "step": "done"}
    if pref != "anyone":
        query["gender"] = pref

    match = await users.find_one(query)
    if match:
        chat_id = f"{user['id']}_{match['id']}"
        await chats.insert_one({"users": [user["id"], match["id"]], "chat_id": chat_id, "active": True})
        await bot.send_message(user["id"], f"💌 You've been matched with {match['name']}!")
        await bot.send_message(match["id"], f"💌 You've been matched with {user['name']}!")
    else:
        await callback.message.answer("No match found right now. Try again later.")

@dp.callback_query(F.data == "random")
async def random_chat(callback):
    await callback.message.answer("🎭 Random chat coming soon (to be implemented)")

@dp.callback_query(F.data == "refer")
async def refer_user(callback):
    uid = callback.from_user.id
    link = f"https://t.me/AnonymalousMatchBot?start={uid}"
    await callback.message.answer(f"📣 Share your referral link:
{link}

Earn surprises for every 5 referrals!")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
