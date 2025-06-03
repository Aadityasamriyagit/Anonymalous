import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
queue = []

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔍 Match", callback_data="match")],
        [InlineKeyboardButton(text="🎭 Random Chat", callback_data="random")],
        [InlineKeyboardButton(text="📣 Refer & Earn", callback_data="refer")],
        [InlineKeyboardButton(text="📝 Edit Profile", callback_data="edit")]
    ])

@dp.message(F.text == "/start")
async def start(message: Message):
    user = await users.find_one({"id": message.from_user.id})
    ref_id = message.text.split(" ")[1] if len(message.text.split(" ")) > 1 else None
    if not user:
        await users.insert_one({"id": message.from_user.id, "step": "name"})
        if ref_id and ref_id.isdigit():
            await referrals.insert_one({"ref": int(ref_id), "joined": message.from_user.id})
        await message.answer("👋 Welcome to Anonymalous!
What is your name?")
    else:
        await message.answer("👋 You're back! Use the menu below.", reply_markup=main_menu())

@dp.message()
async def collect_info(message: Message):
    user = await users.find_one({"id": message.from_user.id})
    if not user or "step" not in user: return

    val = message.text.strip()
    step = user["step"]

    if step == "name":
        await users.update_one({"id": user["id"]}, {"$set": {"name": val, "step": "age"}})
        await message.answer("🎂 What is your exact age?")
    elif step == "age":
        if not val.isdigit():
            await message.answer("❌ Please enter a valid number.")
            return
        await users.update_one({"id": user["id"]}, {"$set": {"age": int(val), "step": "gender"}})
        await message.answer("🚻 Your gender? (Male/Female)")
    elif step == "gender":
        if val.lower() not in ["male", "female"]:
            await message.answer("❌ Choose Male or Female.")
            return
        await users.update_one({"id": user["id"]}, {"$set": {"gender": val.lower(), "step": "preference"}})
        await message.answer("💘 Who are you interested in? (Male/Female/Anyone)")
    elif step == "preference":
        if val.lower() not in ["male", "female", "anyone"]:
            await message.answer("❌ Choose Male, Female or Anyone.")
            return
        await users.update_one({"id": user["id"]}, {"$set": {"preference": val.lower(), "step": "done"}})
        await message.answer("✅ Profile created!", reply_markup=main_menu())

@dp.callback_query(F.data == "match")
async def match(callback: CallbackQuery):
    user = await users.find_one({"id": callback.from_user.id})
    if not user or user.get("step") != "done":
        await callback.message.answer("Complete your profile first using /start.")
        return

    pref = user["preference"]
    query = {"id": {"$ne": user["id"]}, "step": "done"}
    if pref != "anyone":
        query["gender"] = pref

    match = await users.find_one(query)
    if match:
        await chats.insert_one({"users": [user["id"], match["id"]], "active": True})
        await bot.send_message(user["id"], f"💞 Matched with {match['name']} (age {match['age']})")
        await bot.send_message(match["id"], f"💞 Matched with {user['name']} (age {user['age']})")
    else:
        await callback.message.answer("😔 No matches right now. Try again later.")

@dp.callback_query(F.data == "random")
async def random(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id in queue:
        await callback.message.answer("⏳ You're already in the random chat queue.")
        return
    if queue:
        partner_id = queue.pop(0)
        await chats.insert_one({"users": [user_id, partner_id], "active": True})
        await bot.send_message(user_id, "🎭 You are now chatting with a stranger!")
        await bot.send_message(partner_id, "🎭 You are now chatting with a stranger!")
    else:
        queue.append(user_id)
        await callback.message.answer("⏳ Waiting for a stranger...")

@dp.callback_query(F.data == "refer")
async def refer(callback: CallbackQuery):
    link = f"https://t.me/AnonymalousMatchBot?start={callback.from_user.id}"
    count = await referrals.count_documents({"ref": callback.from_user.id})
    await callback.message.answer(f"📣 Your referral link:
{link}
You have referred {count} user(s)!")

@dp.callback_query(F.data == "edit")
async def edit_profile(callback: CallbackQuery):
    await users.update_one({"id": callback.from_user.id}, {"$set": {"step": "name"}})
    await callback.message.answer("📝 Let's update your profile.
What is your name?")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
