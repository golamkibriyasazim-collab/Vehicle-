import os
import json
import time
import asyncio
import logging
from datetime import datetime, timedelta

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
)

# ==================== কনফিগারেশন ====================
BOT_TOKEN = os.getenv("8412861039:AAGerInoGFnUREc1PtCI6w2xYuWbRibcfGw")
ADMIN_IDS = os.getenv("7755338110", "").split(",")
ADMIN_IDS = [id.strip() for id in ADMIN_IDS if id.strip()]

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")
ADMINS_FILE = os.path.join(DATA_DIR, "admins.json")

# কনভারসেশন স্টেট
BROADCAST_STATE, ADD_ADMIN_STATE, REMOVE_ADMIN_STATE = range(3)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ==================== ডেটা হ্যান্ডলিং ====================
def load_json(file_path, default=None):
    if default is None:
        default = {}
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_stats():
    stats = load_json(STATS_FILE, {
        "total_queries": 0,
        "total_users": 0,
        "last_24h_queries": 0,
        "last_24h_users": 0,
        "start_time": int(time.time())
    })
    return stats

def update_stats():
    stats = get_stats()
    stats["total_queries"] += 1
    users = load_json(USERS_FILE, {})
    stats["total_users"] = len(users)
    
    now = int(time.time())
    day_ago = now - 86400
    active_users = 0
    active_queries = 0
    for uid, data in users.items():
        last_seen = data.get("last_seen", 0)
        if last_seen > day_ago:
            active_users += 1
            active_queries += data.get("total_commands", 0)
    
    stats["last_24h_users"] = active_users
    stats["last_24h_queries"] = active_queries
    save_json(STATS_FILE, stats)

def track_user(user_id, username, first_name, last_name):
    users = load_json(USERS_FILE, {})
    user_id = str(user_id)
    now_ts = int(time.time())
    now_str = datetime.now().isoformat()
    
    if user_id not in users:
        users[user_id] = {
            "id": user_id,
            "username": username or "",
            "first_name": first_name or "",
            "last_name": last_name or "",
            "first_seen": now_str,
            "last_seen": now_ts,
            "total_commands": 0
        }
    else:
        users[user_id]["username"] = username or users[user_id]["username"]
        users[user_id]["first_name"] = first_name or users[user_id]["first_name"]
        users[user_id]["last_name"] = last_name or users[user_id]["last_name"]
        # প্রতি ৫ মিনিটে একবার আপডেট করলেই যথেষ্ট (ডেটাবেসের চাপ কমাতে)
        if now_ts - users[user_id].get("last_seen", 0) > 300:
            users[user_id]["last_seen"] = now_ts
    
    users[user_id]["total_commands"] = users[user_id].get("total_commands", 0) + 1
    save_json(USERS_FILE, users)

def is_admin(user_id):
    user_id = str(user_id)
    if user_id in ADMIN_IDS:
        return True
    admins = load_json(ADMINS_FILE, [])
    return user_id in admins

def get_all_admins():
    admins = load_json(ADMINS_FILE, [])
    return list(set(ADMIN_IDS + admins))

def add_admin(user_id):
    user_id = str(user_id)
    admins = load_json(ADMINS_FILE, [])
    if user_id not in admins:
        admins.append(user_id)
        save_json(ADMINS_FILE, admins)
        return True
    return False

def remove_admin(user_id):
    user_id = str(user_id)
    admins = load_json(ADMINS_FILE, [])
    if user_id in admins:
        admins.remove(user_id)
        save_json(ADMINS_FILE, admins)
        return True
    return False

# ==================== গাড়ির তথ্য API ====================
def get_vehicle_info(vehicle_number):
    url = f"https://vvvin-ng.vercel.app/lookup?rc={vehicle_number}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if not data:
            return False

        output = "<b>🚗 যানবাহনের তথ্য 🚗</b>\n\n"

        if "Ownership Details" in data:
            o = data["Ownership Details"]
            output += "<b>👤 মালিকানার বিবরণ</b>\n"
            output += f"• মালিকের নাম: {o.get('Owner Name', 'N/A')}\n"
            output += f"• পিতার নাম: {o.get(\"Father's Name\", 'N/A')}\n"
            output += f"• মালিক ক্রমিক: {o.get('Owner Serial No', 'N/A')}\n"
            output += f"• নিবন্ধন নম্বর: {o.get('Registration Number', 'N/A')}\n"
            output += f"• নিবন্ধিত আরটিও: {o.get('Registered RTO', 'N/A')}\n\n"

        if "Vehicle Details" in data:
            v = data["Vehicle Details"]
            output += "<b>🔧 যানবাহনের বিবরণ</b>\n"
            output += f"• মডেল: {v.get('Model Name', 'N/A')}\n"
            output += f"• প্রস্তুতকারক মডেল: {v.get('Maker Model', 'N/A')}\n"
            output += f"• শ্রেণী: {v.get('Vehicle Class', 'N/A')}\n"
            output += f"• জ্বালানির ধরণ: {v.get('Fuel Type', 'N/A')}\n"
            output += f"• জ্বালানি মান: {v.get('Fuel Norms', 'N/A')}\n"
            output += f"• চেসিস নম্বর: {v.get('Chassis Number', 'N/A')}\n"
            output += f"• ইঞ্জিন নম্বর: {v.get('Engine Number', 'N/A')}\n\n"

        if "Insurance Information" in data:
            i = data["Insurance Information"]
            output += "<b>📄 বীমার তথ্য</b>\n"
            output += f"• বীমা কোম্পানি: {i.get('Insurance Company', 'N/A')}\n"
            output += f"• বীমা নম্বর: {i.get('Insurance No', 'N/A')}\n"
            output += f"• বীমা মেয়াদ: {i.get('Insurance Expiry', 'N/A')}\n"
            output += f"• বীমা পর্যন্ত: {i.get('Insurance Upto', 'N/A')}\n\n"

        if "Important Dates & Validity" in data:
            d = data["Important Dates & Validity"]
            output += "<b>📅 গুরুত্বপূর্ণ তারিখ</b>\n"
            output += f"• নিবন্ধনের তারিখ: {d.get('Registration Date', 'N/A')}\n"
            output += f"• গাড়ির বয়স: {d.get('Vehicle Age', 'N/A')}\n"
            output += f"• ফিটনেস পর্যন্ত: {d.get('Fitness Upto', 'N/A')}\n"
            output += f"• কর পর্যন্ত: {d.get('Tax Upto', 'N/A')}\n"
            output += f"• পিইউসি নম্বর: {d.get('PUC No', 'N/A')}\n"
            output += f"• পিইউসি পর্যন্ত: {d.get('PUC Upto', 'N/A')}\n"
            output += f"• পিইউসি মেয়াদ: {d.get('PUC Expiry In', 'N/A')}\n\n"

        if "Other Information" in data:
            o = data["Other Information"]
            output += "<b>ℹ️ অন্যান্য তথ্য</b>\n"
            output += f"• অর্থদাতা: {o.get('Financer Name', 'N/A')}\n"
            output += f"• সিসি ক্ষমতা: {o.get('Cubic Capacity', 'N/A')}\n"
            output += f"• আসন ক্ষমতা: {o.get('Seating Capacity', 'N/A')}\n"
            output += f"• অনুমতির ধরণ: {o.get('Permit Type', 'N/A')}\n"
            output += f"• ব্ল্যাকলিস্ট স্থিতি: {o.get('Blacklist Status', 'N/A')}\n\n"

        if "Basic Card Info" in data:
            r = data["Basic Card Info"]
            output += "<b>🏢 আরটিও যোগাযোগ</b>\n"
            output += f"• আরটিও কোড: {r.get('Code', 'N/A')}\n"
            output += f"• শহর: {r.get('City Name', 'N/A')}\n"
            output += f"• ফোন: {r.get('Phone', 'N/A')}\n"
            output += f"• ওয়েবসাইট: {r.get('Website', 'N/A')}\n"
            output += f"• ঠিকানা: {r.get('Address', 'N/A')}\n"

        output += "\n━━━━━━━━━━━━━━━━━━━━\n"
        output += "⚡ পাওয়ার্ড বাই রোহিত শর্মা ⚡\n"
        output += "👨‍💻 ডেভেলপার: @FroxtDevil"
        return output
    except Exception as e:
        logger.error(f"API Error: {e}")
        return False

# ==================== কীবোর্ড ====================
def admin_keyboard():
    kb = [
        [InlineKeyboardButton("📊 পরিসংখ্যান", callback_data="stats"),
         InlineKeyboardButton("👥 ইউজার তালিকা", callback_data="users")],
        [InlineKeyboardButton("📢 ব্রডকাস্ট", callback_data="broadcast"),
         InlineKeyboardButton("👑 অ্যাডমিন ব্যবস্থা", callback_data="manage")],
        [InlineKeyboardButton("📝 বট তথ্য", callback_data="info"),
         InlineKeyboardButton("🔄 রিফ্রেশ", callback_data="refresh")],
        [InlineKeyboardButton("❌ বন্ধ", callback_data="close")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_manage_keyboard():
    kb = [
        [InlineKeyboardButton("➕ অ্যাডমিন যোগ", callback_data="add_admin"),
         InlineKeyboardButton("➖ অ্যাডমিন সরান", callback_data="remove_admin")],
        [InlineKeyboardButton("📋 অ্যাডমিন তালিকা", callback_data="list_admins"),
         InlineKeyboardButton("🔙 পিছনে", callback_data="back")]
    ]
    return InlineKeyboardMarkup(kb)

# ==================== হেল্পার ফাংশন ====================
async def send_long_message(context, chat_id, text, parse_mode="HTML", reply_markup=None):
    if len(text) <= 4096:
        await context.bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
    else:
        parts = [text[i:i+4000] for i in range(0, len(text), 4000)]
        for part in parts:
            await context.bot.send_message(chat_id, part, parse_mode=parse_mode)
            await asyncio.sleep(0.1)

async def broadcast_message(context, message, admin_id):
    users = load_json(USERS_FILE, {})
    success = 0
    failed = 0
    for uid in users.keys():
        try:
            await context.bot.send_message(uid, message, parse_mode="HTML")
            success += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)  # রেট লিমিট এড়াতে
    await context.bot.send_message(
        admin_id,
        f"✅ ব্রডকাস্ট শেষ!\n\n📊 পরিসংখ্যান:\n• সফল: {success}\n• ব্যর্থ: {failed}\n• মোট: {len(users)}"
    )

# ==================== কমান্ড হ্যান্ডলার ====================
async def start(update: Update, context):
    user = update.effective_user
    track_user(user.id, user.username, user.first_name, user.last_name)
    text = (
        "🚗 <b>যানবাহন বটে স্বাগতম!</b> 🚗\n\n"
        "গাড়ির নম্বর দিয়ে সব তথ্য জানুন।\n\n"
        "<code>/veh MH12DE1433</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ পাওয়ার্ড বাই রোহিত শর্মা ⚡\n"
        "👨‍💻 @FroxtDevil"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def veh_command(update: Update, context):
    user = update.effective_user
    track_user(user.id, user.username, user.first_name, user.last_name)
    
    if not context.args:
        await update.message.reply_text("❌ সঠিক নম্বর দিন। যেমন: <code>/veh MH12DE1433</code>", parse_mode="HTML")
        return
    
    number = " ".join(context.args).strip()
    if len(number) < 5:
        await update.message.reply_text("❌ নম্বরটি খুব ছোট। সঠিক নম্বর দিন।", parse_mode="HTML")
        return
    
    await update.message.reply_text(f"🔍 <b>{number}</b> খোঁজা হচ্ছে... ⏳", parse_mode="HTML")
    info = get_vehicle_info(number)
    
    if not info:
        await update.message.reply_text(
            "❌ তথ্য পাওয়া যায়নি।\nসঠিক নম্বর দিন: <code>/veh MH12DE1433</code>",
            parse_mode="HTML"
        )
    else:
        await send_long_message(context, update.effective_chat.id, info)
        update_stats()  # শুধু সফল অনুসন্ধান কাউন্ট করি

async def admin_command(update: Update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ অনুমতি নেই! আপনি অ্যাডমিন নন।")
        return
    await update.message.reply_text("🔐 অ্যাডমিন প্যানেল", parse_mode="HTML", reply_markup=admin_keyboard())

async def stats_command(update: Update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ অনুমতি নেই!")
        return
    
    stats = get_stats()
    uptime = int(time.time()) - stats["start_time"]
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    minutes = (uptime % 3600) // 60
    
    text = (
        f"📊 <b>বট পরিসংখ্যান</b>\n\n"
        f"👥 <b>ইউজার:</b>\n• মোট: {stats['total_users']}\n• সক্রিয় (২৪ঘ): {stats['last_24h_users']}\n• খোঁজ (২৪ঘ): {stats['last_24h_queries']}\n\n"
        f"🔍 <b>খোঁজ:</b>\n• মোট: {stats['total_queries']}\n\n"
        f"⏱️ <b>চলমান:</b>\n• {days}দিন {hours}ঘ {minutes}মি\n\n"
        f"📅 <b>শুরু:</b>\n• {datetime.fromtimestamp(stats['start_time']).strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await update.message.reply_text(text, parse_mode="HTML")

async def users_command(update: Update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ অনুমতি নেই!")
        return
    
    users = load_json(USERS_FILE, {})
    total = len(users)
    page = 1
    per_page = 10
    offset = (page - 1) * per_page
    items = list(users.items())[offset:offset+per_page]
    
    text = f"👥 <b>ইউজার তালিকা</b> (পৃষ্ঠা {page})\n\n"
    i = offset + 1
    for uid, data in items:
        name = data.get("first_name", "")
        if data.get("last_name"):
            name += " " + data["last_name"]
        uname = f"@{data['username']}" if data.get("username") else "ইউজারনেম নেই"
        last_seen = datetime.fromtimestamp(data.get("last_seen", 0)).strftime('%Y-%m-%d %H:%M')
        text += f"{i}. <b>{name}</b>\n   আইডি: <code>{uid}</code>\n   {uname}\n   কমান্ড: {data.get('total_commands', 0)}\n   শেষ: {last_seen}\n\n"
        i += 1
    
    text += f"📊 মোট: {total} | 📄 পৃষ্ঠা {page}/{max(1, (total + per_page - 1)//per_page)}"
    await update.message.reply_text(text, parse_mode="HTML")

async def broadcast_command(update: Update, context):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ অনুমতি নেই!")
        return
    await update.message.reply_text("📢 ব্রডকাস্ট মেসেজ লিখুন (বাতিল: /cancel)")
    return BROADCAST_STATE

async def cancel(update: Update, context):
    if context.user_data.get("conversation"):
        context.user_data.pop("conversation")
        await update.message.reply_text("❌ বাতিল করা হয়েছে।")
    else:
        await update.message.reply_text("কোনো চলমান কাজ নেই।")
    return ConversationHandler.END

async def broadcast_receive(update: Update, context):
    user = update.effective_user
    text = update.message.text
    if text == "/cancel":
        await update.message.reply_text("❌ বাতিল করা হয়েছে।")
        return ConversationHandler.END
    
    await update.message.reply_text("📨 ব্রডকাস্ট শুরু হয়েছে... মেসেজটি সবাইকে পাঠানো হচ্ছে (এতে কয়েক সেকেন্ড সময় লাগতে পারে)।")
    await broadcast_message(context, text, user.id)
    return ConversationHandler.END

async def add_admin_receive(update: Update, context):
    user = update.effective_user
    text = update.message.text
    if text == "/cancel":
        await update.message.reply_text("❌ বাতিল করা হয়েছে।")
        return ConversationHandler.END
    
    if not text.isdigit():
        await update.message.reply_text("❌ শুধু নম্বর দিন (ইউজার আইডি)।")
        return ADD_ADMIN_STATE
    
    if add_admin(text):
        await update.message.reply_text(f"✅ অ্যাডমিন যোগ! আইডি: <code>{text}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ ইতিমধ্যে অ্যাডমিন।")
    return ConversationHandler.END

async def remove_admin_receive(update: Update, context):
    user = update.effective_user
    text = update.message.text
    if text == "/cancel":
        await update.message.reply_text("❌ বাতিল করা হয়েছে।")
        return ConversationHandler.END
    
    if not text.isdigit():
        await update.message.reply_text("❌ শুধু নম্বর দিন (ইউজার আইডি)।")
        return REMOVE_ADMIN_STATE
    
    if remove_admin(text):
        await update.message.reply_text(f"✅ অ্যাডমিন সরান! আইডি: <code>{text}</code>", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ এই ইউজার অ্যাডমিন নন।")
    return ConversationHandler.END

# ==================== কলব্যাক হ্যান্ডলার ====================
async def callback_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if not is_admin(user.id):
        await query.edit_message_text("⛔ আপনি অ্যাডমিন নন!")
        return
    
    data = query.data
    chat_id = query.message.chat.id
    
    if data == "stats":
        stats = get_stats()
        uptime = int(time.time()) - stats["start_time"]
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60
        text = (
            f"📊 <b>বট পরিসংখ্যান</b>\n\n"
            f"👥 <b>ইউজার:</b>\n• মোট: {stats['total_users']}\n• সক্রিয় (২৪ঘ): {stats['last_24h_users']}\n• খোঁজ (২৪ঘ): {stats['last_24h_queries']}\n\n"
            f"🔍 <b>খোঁজ:</b>\n• মোট: {stats['total_queries']}\n\n"
            f"⏱️ <b>চলমান:</b>\n• {days}দিন {hours}ঘ {minutes}মি\n\n"
            f"📅 <b>শুরু:</b>\n• {datetime.fromtimestamp(stats['start_time']).strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())
    
    elif data == "users":
        users = load_json(USERS_FILE, {})
        total = len(users)
        page = 1
        per_page = 10
        offset = (page - 1) * per_page
        items = list(users.items())[offset:offset+per_page]
        text = f"👥 <b>ইউজার তালিকা</b> (পৃষ্ঠা {page})\n\n"
        i = offset + 1
        for uid, u in items:
            name = u.get("first_name", "")
            if u.get("last_name"):
                name += " " + u["last_name"]
            uname = f"@{u['username']}" if u.get("username") else "ইউজারনেম নেই"
            last_seen = datetime.fromtimestamp(u.get("last_seen", 0)).strftime('%Y-%m-%d %H:%M')
            text += f"{i}. <b>{name}</b>\n   আইডি: <code>{uid}</code>\n   {uname}\n   কমান্ড: {u.get('total_commands', 0)}\n   শেষ: {last_seen}\n\n"
            i += 1
        text += f"📊 মোট: {total} | 📄 পৃষ্ঠা {page}/{max(1, (total + per_page - 1)//per_page)}"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())
    
    elif data == "broadcast":
        await query.edit_message_text("📢 ব্রডকাস্ট মেসেজ লিখুন (বাতিল: /cancel)")
        return BROADCAST_STATE
    
    elif data == "manage":
        await query.edit_message_text("👑 অ্যাডমিন ব্যবস্থাপনা", parse_mode="HTML", reply_markup=admin_manage_keyboard())
    
    elif data == "add_admin":
        await query.edit_message_text("➕ অ্যাডমিন যোগ করতে ইউজার আইডি পাঠান (বাতিল: /cancel)")
        return ADD_ADMIN_STATE
    
    elif data == "remove_admin":
        await query.edit_message_text("➖ অ্যাডমিন সরাতে ইউজার আইডি পাঠান (বাতিল: /cancel)")
        return REMOVE_ADMIN_STATE
    
    elif data == "list_admins":
        admins = get_all_admins()
        text = "👑 বর্তমান অ্যাডমিন:\n\n"
        for idx, aid in enumerate(admins, 1):
            text += f"{idx}. <code>{aid}</code>\n"
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_manage_keyboard())
    
    elif data == "info":
        text = (
            "🤖 <b>যানবাহন বট</b>\n"
            "ভার্সন ২.০\n"
            "ডেভেলপার: @FroxtDevil\n\n"
            "কমান্ড:\n"
            "/start - শুরু\n"
            "/veh [নম্বর] - তথ্য\n"
            "/admin - অ্যাডমিন প্যানেল\n"
            "/stats - পরিসংখ্যান\n"
            "/users - ইউজার তালিকা\n"
            "/broadcast - ব্রডকাস্ট"
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_keyboard())
    
    elif data == "refresh":
        await query.edit_message_text("🔄 রিফ্রেশ করা হলো!", parse_mode="HTML", reply_markup=admin_keyboard())
    
    elif data == "back":
        await query.edit_message_text("🔙 অ্যাডমিন প্যানেল", parse_mode="HTML", reply_markup=admin_keyboard())
    
    elif data == "close":
        await query.edit_message_text("❌ প্যানেল বন্ধ।")
    
    return ConversationHandler.END

# ==================== মেইন ফাংশন ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # কনভারসেশন হ্যান্ডলার
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("broadcast", broadcast_command),
            CallbackQueryHandler(callback_handler, pattern="^(broadcast|add_admin|remove_admin)$"),
        ],
        states={
            BROADCAST_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_receive)],
            ADD_ADMIN_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_receive)],
            REMOVE_ADMIN_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, remove_admin_receive)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("veh", veh_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("users", users_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(callback_handler))
    
    logger.info("🚀 বট চালু হচ্ছে...")
    app.run_polling()

if __name__ == "__main__":
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN সেট করা হয়নি!")
    else:
        main()
