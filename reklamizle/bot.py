import ssl
import logging
import asyncio
import certifi
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

# Qoşulma sətirini bu iki parametr ilə yenilə:
client = MongoClient(MONGO_URI)
db = client["reklam_botu"]
users_col = db["users"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "İstifadəçi"
    
    # Məlumat bazası əməliyyatı
    user_data = users_col.find_one({"user_id": user_id})
    if not user_data:
        users_col.insert_one({
            "user_id": user_id,
            "username": username,
            "coins": 0.0,
            "watched_ads": 0
        })
    
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

async def main():
    await start_web_server()
    await dp.start_polling(bot)
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    asyncio.run(main())
import os
from aiohttp import web

# Render-in port xətası verməməsi üçün saxta HTTP server
async def start_web_server():
    async def handle(request):
        return web.Response(text="Bot 7/24 aktivdir!")

    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render avtomatik PORT dəyişənini verir, tapmasa 10000 istifadə edir
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
