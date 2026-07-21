import os
import ssl
import logging
import asyncio
import certifi
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from pymongo import MongoClient

# 1. LOGGING QURULUŞU
logging.basicConfig(level=logging.INFO)

# 2. TELEGRAM BOT TOKENİNİZİ BURA YAZIN
BOT_TOKEN = "8768276338:AAFfh99V9NTbc4t1zlqu0RaRAsZeNvtklzc"

# 3. MONGODB BAĞLANTI LİNKİNİZİ BURA YAZIN
MONGO_URI = "mongodb+srv://ehtiramnurullayev697_db_user:pr0xZeAuBRLsC0EY@cluster0.sjqgt0p.mongodb.net/?appName=Cluster0"

# 4. VERCEL-DƏKİ SAYTINIZIN LINKI
VERCEL_URL = "https://reklamizle-orpin.vercel.app"

# Sistem səviyyəsində bütün SSL yoxlamalarını bypass edən kontekst yaradırıq
ssl_context = ssl._create_unverified_context()

# Qoşulma
client = MongoClient(MONGO_URI)
db = client["reklam_botu"]
users_col = db["users"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


def ensure_user_exists(user_id, username=None, extra_data=None):
    try:
        telegram_id = int(user_id)
    except (TypeError, ValueError):
        return None

    user_data = users_col.find_one({"$or": [{"telegram_id": telegram_id}, {"user_id": telegram_id}]})

    if not user_data:
        user_doc = {
            "user_id": telegram_id,
            "telegram_id": telegram_id,
            "username": username or "İstifadəçi",
            "coins": 0.0,
            "watched_ads": 0
        }
        if extra_data:
            user_doc.update(extra_data)
        users_col.insert_one(user_doc)
        return user_doc

    update_data = {"$set": {"telegram_id": telegram_id}}
    if username:
        update_data["$set"]["username"] = username
    if extra_data:
        update_data["$set"].update(extra_data)

    users_col.update_one({"_id": user_data["_id"]}, update_data)
    user_data["telegram_id"] = telegram_id
    if username:
        user_data["username"] = username
    return user_data


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "İstifadəçi"

    ensure_user_exists(user_id, username=username)

    web_app = WebAppInfo(url=f"{VERCEL_URL}?user_id={user_id}")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Reklam İzlə və Qazan", web_app=web_app)]
    ])

    await message.reply(
        f"Salam, {username}! 👋\n\n"
        f"Platformamıza xoş gəldiniz. Aşağıdakı düyməyə klikləyərək reklam izləyib coin qazana bilərsiniz. "
        f"Balansınız və məlumatlarınız 24/7 bazada qorunur!",
        reply_markup=keyboard
    )


# CORS dəstəyi üçün cavab yaradan köməkçi funksiya
def cors_json_response(data):
    return web.json_response(data, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    })


# Render üçün Web Server (Port və API handlerlər)
async def start_web_server():
    async def handle(request):
        return web.Response(text="Bot 7/24 aktivdir!", headers={"Access-Control-Allow-Origin": "*"})

    async def check_user(request):
        telegram_id = request.query.get("telegram_id")
        if not telegram_id:
            return cors_json_response({"is_registered": False})

        try:
            telegram_id_value = int(telegram_id)
        except (ValueError, TypeError):
            return cors_json_response({"is_registered": False})

        user = users_col.find_one({"$or": [{"telegram_id": telegram_id_value}, {"user_id": telegram_id_value}]})
        if user:
            return cors_json_response({
                "is_registered": True,
                "username": user.get("username"),
                "coins": user.get("coins", 0)
            })

        return cors_json_response({"is_registered": False})

    async def register_user(request):
        if request.method == "OPTIONS":
            return cors_json_response({"ok": True})

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        if not payload:
            payload = dict(request.query)

        telegram_id = payload.get("telegram_id") or payload.get("user_id")
        username = payload.get("username") or payload.get("name") or "İstifadəçi"

        if not telegram_id:
            return cors_json_response({"ok": False, "message": "telegram_id is required"})

        try:
            telegram_id_value = int(telegram_id)
        except (ValueError, TypeError):
            return cors_json_response({"ok": False, "message": "telegram_id must be numeric"})

        ensure_user_exists(telegram_id_value, username=username)
        return cors_json_response({"ok": True, "message": "registered"})

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/check_user", check_user)
    app.router.add_get("/register_user", register_user)
    app.router.add_post("/register_user", register_user)
    app.router.add_options("/register_user", register_user)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()


async def main():
    await start_web_server()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
