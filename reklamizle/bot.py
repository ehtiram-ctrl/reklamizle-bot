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
import random
from datetime import datetime, timedelta
import asyncio

# 1. LOGGING QURULUŞU
logging.basicConfig(level=logging.INFO)

# 2. TELEGRAM BOT TOKENİNİZİ BURA YAZIN
BOT_TOKEN = "8768276338:AAFfh99V9NTbc4t1zlqu0RaRAsZeNvtklzc"

# Çərçivə qiymətləri — YALNIZ server bunu bilir, client-in göndərdiyi qiymətə güvənilmir
FRAME_PRICES = {
    "frame-blue": 20,
    "frame-red": 20,
    "frame-green": 20,
    "frame-yellow": 20,
    "frame-gold": 100,
    "frame-diamond": 200
}

# 3. MONGODB BAĞLANTI LİNKİNİZİ BURA YAZIN
MONGO_URI = "mongodb+srv://ehtiramnurullayev697_db_user:pr0xZeAuBRLsC0EY@cluster0.sjqgt0p.mongodb.net/?appName=Cluster0"

# 4. VERCEL-DƏKİ SAYTINIZIN LINKI
VERCEL_URL = "https://reklamizle-orpin.vercel.app"

# Çəkim tələbləri bura göndəriləcək — öz Telegram ID-nizi yazın
ADMIN_TELEGRAM_ID = 6326355120  # BURAYA ÖZ TELEGRAM ID-NİZİ YAZIN

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
    allowed_fields = ["avatar", "referrals"]
    
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

async def join_wheel(request):
    """İstifadəçini çarxa əlavə et"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})
    
    try:
        payload = await request.json()
    except:
        payload = {}
    
    telegram_id = payload.get("telegram_id")
    if not telegram_id:
        return cors_json_response({"ok": False, "message": "telegram_id required"})
    
    try:
        telegram_id = int(telegram_id)
    except:
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})
    
    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return cors_json_response({"ok": False, "message": "user not found"})
    
    # Qeydiyyat yoxla
    if not user.get("registered_username"):
        return cors_json_response({"ok": False, "message": "register first"})
    
    # Balans yoxla
    if user.get("coins", 0) < 20:
        return cors_json_response({"ok": False, "message": "insufficient balance"})
    
    # Bu həftə artıq qoşulubmu?
    now = datetime.now()
    current_week = now.strftime("%Y-W%U")
    
    wheel_doc = db["wheel"].find_one({"week": current_week})
    
    if wheel_doc:
        participants = wheel_doc.get("participants", [])
        if any(p["telegram_id"] == telegram_id for p in participants):
            return cors_json_response({"ok": False, "message": "already joined this week"})
    
    # Balansdan 20 çıx
    new_balance = user.get("coins", 0) - 20
    users_col.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"coins": round(new_balance, 2)}}
    )
    
    # Çarxa əlavə et
    participant = {
        "telegram_id": telegram_id,
        "username": user.get("registered_username", "Unknown"),
        "frame": user.get("frame", "frame-none"),
        "joined_at": now
    }
    
    if wheel_doc:
        db["wheel"].update_one(
            {"week": current_week},
            {"$push": {"participants": participant}}
        )
    else:
        db["wheel"].insert_one({
            "week": current_week,
            "participants": [participant],
            "winner": None,
            "spun": False,
            "total_pool": 20
        })
    
    return cors_json_response({"ok": True, "new_balance": round(new_balance, 2)})

async def claim_ad_reward(request):
    """Reklam mükafatını TAMAMILƏ server tərəfdə hesablayır (client-ə güvənmir)"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        return cors_json_response({"ok": False, "message": "invalid json"})

    telegram_id = payload.get("telegram_id")
    ad_slot = payload.get("ad_slot")

    if not telegram_id or ad_slot not in (1, 2):
        return cors_json_response({"ok": False, "message": "invalid parameters"})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return cors_json_response({"ok": False, "message": "user not found"})

    today = datetime.now().strftime("%Y-%m-%d")
    limits = user.get("daily_limits", {})
    if limits.get("last_date") != today:
        limits = {"ad1": 50, "ad2": 50, "last_date": today}

    limit_key = f"ad{ad_slot}"
    if limits.get(limit_key, 0) <= 0:
        return cors_json_response({"ok": False, "message": "limit finished"})

    reward = round(random.uniform(5.00, 6.00), 2)
    limits[limit_key] -= 1
    new_balance = round(user.get("coins", 0.0) + reward, 2)

    users_col.update_one(
        {"telegram_id": telegram_id},
        {"$set": {"coins": new_balance, "daily_limits": limits}}
    )

    return cors_json_response({
        "ok": True,
        "reward": reward,
        "new_balance": new_balance,
        "daily_limits": limits
    })

async def buy_frame(request):
    """Çərçivə alışını TAMAMILƏ server tərəfdə edir"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        return cors_json_response({"ok": False, "message": "invalid json"})

    telegram_id = payload.get("telegram_id")
    frame_class = payload.get("frame_class")

    if not telegram_id or frame_class not in FRAME_PRICES:
        return cors_json_response({"ok": False, "message": "invalid parameters"})

    try:
        telegram_id = int(telegram_id)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid telegram_id"})

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return cors_json_response({"ok": False, "message": "user not found"})

    owned_frames = user.get("owned_frames", ["frame-none"])

    # Artıq alınıbsa — pulsuz tətbiq et
    if frame_class in owned_frames:
        users_col.update_one({"telegram_id": telegram_id}, {"$set": {"frame": frame_class}})
        return cors_json_response({
            "ok": True,
            "already_owned": True,
            "frame": frame_class,
            "owned_frames": owned_frames,
            "new_balance": user.get("coins", 0.0)
        })

    cost = FRAME_PRICES[frame_class]
    current_balance = user.get("coins", 0.0)

    if current_balance < cost:
        return cors_json_response({"ok": False, "message": "insufficient balance"})

    new_balance = round(current_balance - cost, 2)
    owned_frames.append(frame_class)

    users_col.update_one(
        {"telegram_id": telegram_id},
        {"$set": {
            "coins": new_balance,
            "owned_frames": owned_frames,
            "frame": frame_class
        }}
    )

    return cors_json_response({
        "ok": True,
        "already_owned": False,
        "frame": frame_class,
        "owned_frames": owned_frames,
        "new_balance": new_balance
    })

async def request_withdraw(request):
    """Pul çıxarma tələbini TAMAMILƏ server tərəfdə yoxlayır və balansdan çıxır"""
    if request.method == "OPTIONS":
        return cors_json_response({"ok": True})

    try:
        payload = await request.json()
    except Exception:
        return cors_json_response({"ok": False, "message": "invalid json"})

    telegram_id = payload.get("telegram_id")
    card = payload.get("card", "").strip()
    amount = payload.get("amount")

    if not telegram_id or not card or amount is None:
        return cors_json_response({"ok": False, "message": "missing parameters"})

    try:
        telegram_id = int(telegram_id)
        amount = float(amount)
    except (ValueError, TypeError):
        return cors_json_response({"ok": False, "message": "invalid parameters"})

    import re
    is_valid_card = bool(
        re.match(r"^\d{16}$", card) or
        re.match(r"^TRC20:", card, re.IGNORECASE) or
        re.match(r"^0x[a-fA-F0-9]{20,}$", card)
    )
    if not is_valid_card:
        return cors_json_response({"ok": False, "message": "invalid card"})

    if amount < 12500:
        return cors_json_response({"ok": False, "message": "below minimum limit"})

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return cors_json_response({"ok": False, "message": "user not found"})

    if not user.get("registered_username"):
        return cors_json_response({"ok": False, "message": "register first"})

    current_balance = user.get("coins", 0.0)
    if amount > current_balance:
        return cors_json_response({"ok": False, "message": "insufficient balance"})

    new_balance = round(current_balance - amount, 2)
    users_col.update_one({"telegram_id": telegram_id}, {"$set": {"coins": new_balance}})

    db["withdrawals"].insert_one({
        "telegram_id": telegram_id,
        "username": user.get("registered_username"),
        "card": card,
        "coins": amount,
        "usd": round(amount / 12500, 2),
        "status": "pending",
        "created_at": datetime.now()
    })

    try:
        await bot.send_message(
            chat_id=telegram_id,
            text=f"✅ Çəkim tələbiniz qəbul edildi: {amount:.2f} COIN ({round(amount/12500, 2)}$). Tezliklə baxılacaq."
        )
    except:
        pass

    try:
        await bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=(
                f"💰 YENİ ÇƏKİM TƏLƏBİ\n\n"
                f"İstifadəçi: {user.get('registered_username')}\n"
                f"Telegram ID: {telegram_id}\n"
                f"Kart/Ünvan: {card}\n"
                f"Məbləğ: {amount:.2f} COIN ({round(amount/12500, 2)}$)\n"
                f"Qalan balans: {new_balance:.2f} COIN"
            )
        )
    except:
        pass

    return cors_json_response({"ok": True, "new_balance": new_balance})

async def get_wheel_status(request):
    """Çarx statusunu qaytar"""
    telegram_id = request.query.get("telegram_id")
    
    now = datetime.now()
    current_week = now.strftime("%Y-W%U")
    
    wheel_doc = db["wheel"].find_one({"week": current_week})
    
    participants = []
    is_joined = False
    total_pool = 0
    
    if wheel_doc:
        participants = wheel_doc.get("participants", [])
        total_pool = len(participants) * 20
        if telegram_id:
            try:
                tid = int(telegram_id)
                is_joined = any(p["telegram_id"] == tid for p in participants)
            except:
                pass
    
    # Son qalibi tap
    last_winner = None
    last_week = (now - timedelta(days=7)).strftime("%Y-W%U")
    last_wheel = db["wheel"].find_one({"week": last_week, "winner": {"$ne": None}})
    
    if last_wheel and last_wheel.get("winner"):
        w = last_wheel["winner"]
        last_winner = {
            "username": w.get("username", "Unknown"),
            "frame": w.get("frame", "frame-none"),
            "amount": w.get("amount", 0)
        }
    
    # Növbəti fırlanma vaxtı
    next_spin = get_next_spin_time()
    
    return cors_json_response({
        "ok": True,
        "participants": participants,
        "total_pool": total_pool,
        "is_joined": is_joined,
        "last_winner": last_winner,
        "next_spin": next_spin.isoformat(),
        "participant_count": len(participants)
    })


def get_next_spin_time():
    """Növbəti bazar günü 12:00"""
    now = datetime.now()
    days_until_sunday = (6 - now.weekday()) % 7
    if days_until_sunday == 0 and now.hour >= 12:
        days_until_sunday = 7
    next_sunday = now + timedelta(days=days_until_sunday)
    return next_sunday.replace(hour=12, minute=0, second=0, microsecond=0)


async def spin_wheel():
    """Çarxı fırlat (avtomatik çağrılacaq)"""
    now = datetime.now()
    last_week = (now - timedelta(days=7)).strftime("%Y-W%U")
    
    wheel_doc = db["wheel"].find_one({"week": last_week})
    
    if not wheel_doc or wheel_doc.get("spun", False):
        return
    
    participants = wheel_doc.get("participants", [])
    
    if len(participants) == 0:
        # Heç kim yoxdur
        db["wheel"].update_one({"week": last_week}, {"$set": {"spun": True}})
        return
    
    if len(participants) == 1:
        # Yalnız 1 nəfər var — 20 coin-i geri qaytar
        p = participants[0]
        user = users_col.find_one({"telegram_id": p["telegram_id"]})
        if user:
            new_balance = user.get("coins", 0) + 20
            users_col.update_one(
                {"telegram_id": p["telegram_id"]},
                {"$set": {"coins": round(new_balance, 2)}}
            )
        db["wheel"].update_one({"week": last_week}, {"$set": {"spun": True, "refunded": True}})
        return
    
    # Qalib seç (random)
    winner = random.choice(participants)
    total_pool = len(participants) * 20
    prize = round(total_pool * 0.7, 2)  # 70%
    system_keep = round(total_pool * 0.3, 2)  # 30% sistemdə qalır
    
    # Qalibin balansına əlavə et
    user = users_col.find_one({"telegram_id": winner["telegram_id"]})
    if user:
        new_balance = user.get("coins", 0) + prize
        users_col.update_one(
            {"telegram_id": winner["telegram_id"]},
            {"$set": {"coins": round(new_balance, 2)}}
        )
    
    # Qalibi yaz
    db["wheel"].update_one(
        {"week": last_week},
        {"$set": {
            "spun": True,
            "winner": {
                "telegram_id": winner["telegram_id"],
                "username": winner["username"],
                "frame": winner["frame"],
                "amount": prize
            },
            "prize": prize,
            "system_keep": system_keep
        }}
    )
    
    # Qalibə bildiriş göndər (optional)
    try:
        await bot.send_message(
            chat_id=winner["telegram_id"],
            text=f"🎉 Təbriklər! Çarxda {prize} COIN qazandınız!"
        )
    except:
        pass

# ============ WEB SERVER ============
async def start_web_server():
    app = web.Application()
    
    # Routes
    app.router.add_post("/join_wheel", join_wheel)
    app.router.add_options("/join_wheel", join_wheel)
    app.router.add_get("/wheel_status", get_wheel_status)
    app.router.add_get("/wheel_status", get_wheel_status)
    app.router.add_post("/claim_ad_reward", claim_ad_reward)
    app.router.add_options("/claim_ad_reward", claim_ad_reward)
    app.router.add_get("/", handle)
    app.router.add_get("/get_user_data", get_user_data)
    app.router.add_post("/register_user_full", register_user_full)
    app.router.add_options("/register_user_full", register_user_full)
    app.router.add_post("/update_profile", update_profile)
    app.router.add_options("/update_profile", update_profile)
    app.router.add_post("/buy_frame", buy_frame)
    app.router.add_options("/buy_frame", buy_frame)
    app.router.add_post("/request_withdraw", request_withdraw)
    app.router.add_options("/request_withdraw", request_withdraw)
    app.router.add_get("/check_user", check_user)
    app.router.add_get("/register_user", register_user)
    app.router.add_post("/register_user", register_user)
    app.router.add_options("/register_user", register_user)
    app.router.add_get("/leaderboard", get_leaderboard)
    app.router.add_get("/get_leaderboard", get_leaderboard)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


async def main():
    await start_web_server()
    
    # Hər dəqiqə yoxla — bazar günü 12:00-dırmı?
    async def wheel_scheduler():
        while True:
            now = datetime.now()
            if now.weekday() == 6 and now.hour == 12 and now.minute == 0:
                await spin_wheel()
                await asyncio.sleep(61)  # 1 dəqiqə gözlə (təkrarlanmasın)
            await asyncio.sleep(30)  # Hər 30 saniyədə yoxla
    
    asyncio.create_task(wheel_scheduler())
    await dp.start_polling(bot, skip_updates=True)


if __name__ == '__main__':
    asyncio.run(main())
