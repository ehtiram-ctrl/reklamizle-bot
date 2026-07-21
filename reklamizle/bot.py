import os
import ssl
import logging
import asyncio
import certifi
from datetime import datetime, timedelta
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from pymongo import MongoClient
from bson import ObjectId

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

    user_data = users_col.find_one({"telegram_id": telegram_id})

    if not user_data:
        user_doc = {
            "telegram_id": telegram_id,
            "username": username or "İstifadəçi",
            "coins": 0.0,
            "watched_ads": 0,
            "registered_username": None,
            "password": None,
            "frame": "frame-none",
            "avatar": "",
            "owned_frames": ["frame-none"],
            "daily_limits": {
                "ad1": 50,
                "ad2": 50,
                "last_date": datetime.now().strftime("%Y-%m-%d")
            },
            "wheel_participants": [],
            "referrals": [],
            "invited_by": None,
            "created_at": datetime.now()
        }
        if extra_data:
            user_doc.update(extra_data)
        users_col.insert_one(user_doc)
        return user_doc

    update_data = {"$set": {}}
    if username:
        update_data["$set"]["username"] = username
    if extra_data:
        update_data["$set"].update(extra_data)
    
    if update_data["$set"]:
        users_col.update_one({"_id": user_data["_id"]}, update_data)
        user_data.update(update_data["$set"])
    
    return user_data


def cors_json_response(data):
    return web.json_response(data, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    })


@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "İstifadəçi"
    
    # Referral yoxlaması
    args = message.text.split()
    invited_by = None
    if len(args) > 1 and args[1].startswith("ref_"):
        invited_by = args[1].replace("ref_", "")
    
    extra = {}
    if invited_by:
        extra["invited_by"] = invited_by
    
    ensure_user_exists(user_id, username=username, extra_data=extra)

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


# ============ API ENDPOINTLƏRİ ============

async def handle(request):
    return web.Response(text="Bot 7/24 aktivdir!", headers={"Access-Control-Allow-Origin": "*"})


async def get_user_data(request):
    """Bütün istifadəçi məlumatlarını qaytarır"""
    telegram_id = request.query.get("telegram_id")
    if not telegram_id:
        return cors_json_response({"ok": False, "message": "telegram_id required"})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return cors_json_response({"ok": False, "message": "user not found"})

    # Günlük limitləri yoxla və sıfırla
    today = datetime.now().strftime("%Y-%m-%d")
    limits = user.get("daily_limits", {})
    if limits.get("last_date") != today:
        limits = {"ad1": 50, "ad2": 50, "last_date": today}
        users_col.update_one({"telegram_id": telegram_id}, {"$set": {"daily_limits": limits}})

    # ObjectId JSON serializable deyil, ona görə _id-ni string edirik
    user_data = {
        "ok": True,
        "telegram_id": user["telegram_id"],
        "username": user.get("username", "İstifadəçi"),
        "registered_username": user.get("registered_username"),
        "coins": user.get("coins", 0.0),
        "frame": user.get("frame", "frame-none"),
        "avatar": user.get("avatar", ""),
        "owned_frames": user.get("owned_frames", ["frame-none"]),
        "daily_limits": limits,
        "wheel_participants": user.get("wheel_participants", []),
        "referrals": user.get("referrals", []),
        "invited_by": user.get("invited_by"),
        "watched_ads": user.get("watched_ads", 0)
    }
    
    return cors_json_response(user_data)


async def update_balance(request):
    """Balansı yeniləyir"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        return cors_json_response({"ok": False, "message": "invalid json"})

    telegram_id = payload.get("telegram_id")
    amount = payload.get("amount")
    operation = payload.get("operation", "add")  # "add" or "set"

    if not telegram_id or amount is None:
        return cors_json_response({"ok": False, "message": "telegram_id and amount required"})

    try:
        telegram_id = int(telegram_id)
        amount = float(amount)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid parameters"})

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return cors_json_response({"ok": False, "message": "user not found"})

    if operation == "add":
        new_balance = user.get("coins", 0.0) + amount
    else:
        new_balance = amount

    users_col.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"coins": round(new_balance, 2)}}
    )

    return cors_json_response({"ok": True, "new_balance": round(new_balance, 2)})


async def update_limits(request):
    """Günlük limitləri yeniləyir"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        return cors_json_response({"ok": False, "message": "invalid json"})

    telegram_id = payload.get("telegram_id")
    limits = payload.get("limits")

    if not telegram_id or not limits:
        return cors_json_response({"ok": False, "message": "missing parameters"})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})

    users_col.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"daily_limits": limits}}
    )

    return cors_json_response({"ok": True})


async def register_user_full(request):
    """Tam qeydiyyat (username + password)"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        payload = {}

    telegram_id = payload.get("telegram_id")
    reg_username = payload.get("username")
    password = payload.get("password")

    if not telegram_id or not reg_username:
        return cors_json_response({"ok": False, "message": "missing parameters"})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})

    users_col.update_one(
        {"telegram_id": telegram_id},
        {"$set": {
            "registered_username": reg_username,
            "password": password  # Real app-da hash edin!
        }}
    )

    return cors_json_response({"ok": True, "message": "registered"})


async def update_profile(request):
    """Profil məlumatlarını yeniləyir (frame, avatar, etc.)"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        return cors_json_response({"ok": False, "message": "invalid json"})

    telegram_id = payload.get("telegram_id")
    if not telegram_id:
        return cors_json_response({"ok": False, "message": "telegram_id required"})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})

    update_fields = {}
    allowed_fields = ["frame", "avatar", "owned_frames", "wheel_participants", "referrals"]
    
    for field in allowed_fields:
        if field in payload:
            update_fields[field] = payload[field]

    if update_fields:
        users_col.update_one(
            {"telegram_id": telegram_id},
            {"$set": update_fields}
        )

    return cors_json_response({"ok": True})


async def check_user(request):
    """Sadə qeydiyyat yoxlaması"""
    telegram_id = request.query.get("telegram_id")
    if not telegram_id:
        return cors_json_response({"is_registered": False})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"is_registered": False})

    user = users_col.find_one({"telegram_id": telegram_id})
    if user and user.get("registered_username"):
        return cors_json_response({
            "is_registered": True,
            "username": user.get("registered_username"),
            "coins": user.get("coins", 0)
        })

    return cors_json_response({"is_registered": False})


async def register_user(request):
    """Köhnə qeydiyyat endpointi (geriyə uyğunluq üçün)"""
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
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "telegram_id must be numeric"})

    ensure_user_exists(telegram_id, username=username)
    return cors_json_response({"ok": True, "message": "registered"})

async def get_leaderboard(request):
    users = list(users_col.find(
        {"registered_username": {"$ne": None}},
        {"registered_username": 1, "coins": 1, "frame": 1, "avatar": 1}
    ).sort("coins", -1).limit(100))
    
    leaderboard = []
    for u in users:
        leaderboard.append({
            "name": u.get("registered_username", "Unknown"),
            "score": round(u.get("coins", 0)),
            "frame": u.get("frame", "frame-none"),
            "avatar": u.get("avatar", ""),
            "isReal": True
        })
    
    return cors_json_response({"ok": True, "leaderboard": leaderboard})
# ============ WEB SERVER ============

async def start_web_server():
    app = web.Application()
    
    # Routes
    app.router.add_get("/", handle)
    app.router.add_get("/get_user_data", get_user_data)
    app.router.add_post("/update_balance", update_balance)
    app.router.add_options("/update_balance", update_balance)
    app.router.add_post("/update_limits", update_limits)
    app.router.add_options("/update_limits", update_limits)
    app.router.add_post("/register_user_full", register_user_full)
    app.router.add_options("/register_user_full", register_user_full)
    app.router.add_post("/update_profile", update_profile)
    app.router.add_options("/update_profile", update_profile)
    app.router.add_get("/check_user", check_user)
    app.router.add_get("/register_user", register_user)
    app.router.add_post("/register_user", register_user)
    app.router.add_options("/register_user", register_user)
    app.router.add_get("/leaderboard", get_leaderboard)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


async def main():
    await start_web_server()
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
