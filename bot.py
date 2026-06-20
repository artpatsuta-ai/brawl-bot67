import telebot
import sqlite3
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, LabeledPrice, ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv 

load_dotenv("env.txt")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CHANNEL_ID = os.getenv("CHANNEL_ID", "@rewjebs")
CHANNEL_LINK = "https://t.me/rewjebs"
CARD_NUMBER = os.getenv("CARD_NUMBER", "5309 2127 7225 3116")
STARS_USERNAME = os.getenv("STARS_USERNAME", "@aironqq")
UAH_TO_STARS = float(os.getenv("UAH_TO_STARS", 1.5))
COMMISSION_PERCENT = 30

bot = telebot.TeleBot(BOT_TOKEN)

bot_online = True
pending_orders = {}
pending_reviews = {}
order_counter = 1
add_data = {}

IMAGES_DIR = Path("images")
IMAGES_DIR.mkdir(exist_ok=True)

def init_db():
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            trophies INTEGER,
            brawlers INTEGER,
            price_uah INTEGER NOT NULL,
            login TEXT NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            media TEXT,
            seller_id INTEGER,
            seller_price INTEGER,
            sold BOOLEAN DEFAULT 0,
            reserved BOOLEAN DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            account_id INTEGER NOT NULL,
            purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            payment_method TEXT,
            currency TEXT,
            amount INTEGER,
            review TEXT,
            review_media TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            purchase_id INTEGER NOT NULL,
            text TEXT,
            media_file_id TEXT,
            media_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (purchase_id) REFERENCES purchases (id)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0,
            total_sold INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sell_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            trophies INTEGER,
            brawlers INTEGER,
            price INTEGER NOT NULL,
            media TEXT,
            login TEXT,
            password TEXT,
            email TEXT,
            status TEXT DEFAULT 'pending',
            admin_price INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def back_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=1, resize_keyboard=True)
    keyboard.add(KeyboardButton("🔙 Назад"))
    return keyboard

def main_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        KeyboardButton("🛒 Витрина"),
        KeyboardButton("🔍 Поиск"),
        KeyboardButton("📊 Мой профиль"),
        KeyboardButton("⭐ Отзывы"),
        KeyboardButton("📤 Сдать аккаунт"),
        KeyboardButton("🟢 Онлайн")
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard():
    keyboard = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    buttons = [
        KeyboardButton("👑 Админ-панель"),
        KeyboardButton("📋 Заявки на продажу"),
        KeyboardButton("📋 Заявки на покупку"),
        KeyboardButton("🔄 Онлайн/Оффлайн"),
        KeyboardButton("🔙 Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_balance(user_id):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else 0

def add_balance(user_id, amount):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO users (user_id, balance) VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET balance = balance + ?
    """, (user_id, amount, amount))
    conn.commit()
    conn.close()

def safe_send_message(chat_id, text, reply_markup=None, parse_mode=None, delete_old_msg_id=None):
    if delete_old_msg_id:
        try:
            bot.delete_message(chat_id, delete_old_msg_id)
        except:
            pass
    return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

def send_gift(chat_id, stars_count):
    try:
        prices = [LabeledPrice(label=f"Подарок {stars_count}⭐", amount=stars_count)]
        bot.send_invoice(
            chat_id=chat_id,
            title=f"🎁 Подарок на {stars_count} ⭐",
            description=f"Перешлите этот подарок на @aironqq для оплаты аккаунта",
            invoice_payload=f"gift_{stars_count}_{chat_id}",
            provider_token="",
            currency="XTR",
            prices=prices,
            start_parameter="gift"
        )
        return True
    except Exception as e:
        print(f"Ошибка отправки подарка: {e}")
        return False

def get_menu_keyboard(user_id):
    if is_admin(user_id):
        return admin_keyboard()
    return main_keyboard()

def main_menu(user_id):
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = [
        InlineKeyboardButton("🛒 Витрина", callback_data="show_shop"),
        InlineKeyboardButton("🔍 Поиск", callback_data="search_menu"),
        InlineKeyboardButton("📊 Мой профиль", callback_data="my_profile"),
        InlineKeyboardButton("⭐ Отзывы", url=CHANNEL_LINK),
        InlineKeyboardButton("📤 Сдать аккаунт", callback_data="sell_account"),
        InlineKeyboardButton("🟢 Онлайн", callback_data="check_online")
    ]
    if is_admin(user_id):
        buttons.append(InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel"))
        buttons.append(InlineKeyboardButton("📋 Заявки на продажу", callback_data="admin_sell_requests"))
        buttons.append(InlineKeyboardButton("📋 Заявки на покупку", callback_data="admin_orders"))
    keyboard.add(*buttons)
    return keyboard

def admin_panel_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = [
        InlineKeyboardButton("➕ Добавить аккаунт", callback_data="admin_add"),
        InlineKeyboardButton("📋 Список аккаунтов", callback_data="admin_list"),
        InlineKeyboardButton("🗑 Удалить аккаунт", callback_data="admin_delete"),
        InlineKeyboardButton("📋 Заявки на продажу", callback_data="admin_sell_requests"),
        InlineKeyboardButton("📋 Заявки на покупку", callback_data="admin_orders"),
        InlineKeyboardButton("🔄 Онлайн/Оффлайн", callback_data="toggle_online"),
    ]
    keyboard.add(*buttons)
    return keyboard

def search_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = [
        InlineKeyboardButton("🔎 По названию", callback_data="search_by_name"),
        InlineKeyboardButton("🏆 По трофеям (мин.)", callback_data="search_by_trophies"),
        InlineKeyboardButton("💰 По цене (макс.)", callback_data="search_by_price"),
    ]
    keyboard.add(*buttons)
    return keyboard

def payment_keyboard(account_name, price_uah, price_stars, order_id):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(f"💳 {price_uah} ₴ (Карта)", callback_data=f"pay_card_{order_id}"),
        InlineKeyboardButton(f"⭐ {price_stars} ⭐ (Подарок)", callback_data=f"pay_stars_{order_id}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_order_{order_id}")
    )
    return keyboard

def account_card(acc_id, name, trophies, brawlers, price_uah, sold):
    status = "🔴 ПРОДАНО" if sold else "🟢 В НАЛИЧИИ"
    price_stars = int(price_uah * UAH_TO_STARS)
    text = (
        f"🏆 {name}\n"
        f"Трофеи: {trophies}\n"
        f"Бравлеры: {brawlers}\n"
        f"💰 Цена: {price_uah} ₴ / {price_stars} ⭐\n"
        f"Статус: {status}"
    )
    return text

def send_media_group(chat_id, media_str, caption, keyboard):
    if not media_str:
        bot.send_message(chat_id, caption, reply_markup=keyboard)
        return
    media_files = media_str.split("|||")
    media_group = []
    for file_path in media_files:
        if not os.path.exists(file_path):
            continue
        if file_path.endswith(('.mp4', '.mov', '.avi', '.mkv')):
            with open(file_path, 'rb') as video:
                bot.send_video(chat_id, video, caption=caption, reply_markup=keyboard)
            return
        else:
            media_group.append(InputMediaPhoto(open(file_path, 'rb')))
    if media_group:
        bot.send_media_group(chat_id, media_group)
        bot.send_message(chat_id, caption, reply_markup=keyboard)
    else:
        bot.send_message(chat_id, caption, reply_markup=keyboard)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(
        message,
        "🏪 Добро пожаловать в магазин аккаунтов Brawl Stars!\nВыберите действие:",
        reply_markup=get_menu_keyboard(message.from_user.id)
    )
    bot.send_message(
        message.chat.id,
        "📌 Используйте кнопки ниже для навигации:",
        reply_markup=main_menu(message.from_user.id)
    )

@bot.message_handler(func=lambda message: message.text == "🔙 Назад")
def back_to_menu(message):
    user_id = message.from_user.id
    bot.send_message(
        message.chat.id,
        "🏪 Главное меню:",
        reply_markup=get_menu_keyboard(user_id)
    )
    bot.send_message(
        message.chat.id,
        "📌 Выберите действие:",
        reply_markup=main_menu(user_id)
    )

@bot.message_handler(func=lambda message: message.text == "🛒 Витрина")
def show_shop_menu(message):
    if not bot_online:
        bot.send_message(message.chat.id, "🔴 Бот временно отключен.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    show_shop_text(message)

@bot.message_handler(func=lambda message: message.text == "🔍 Поиск")
def search_menu_text(message):
    bot.send_message(
        message.chat.id,
        "🔍 Выберите тип поиска:",
        reply_markup=search_keyboard()
    )
    bot.send_message(
        message.chat.id,
        "🔙 Нажмите 'Назад' для возврата",
        reply_markup=back_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📊 Мой профиль")
def profile_menu(message):
    my_profile_text(message)

@bot.message_handler(func=lambda message: message.text == "⭐ Отзывы")
def reviews_menu(message):
    bot.send_message(
        message.chat.id,
        f"📢 Смотреть отзывы можно в нашем канале: {CHANNEL_LINK}",
        reply_markup=get_menu_keyboard(message.from_user.id)
    )

@bot.message_handler(func=lambda message: message.text == "📤 Сдать аккаунт")
def sell_menu(message):
    sell_account_text(message)

@bot.message_handler(func=lambda message: message.text == "🟢 Онлайн")
def online_check(message):
    status = "🟢 Бот работает" if bot_online else "🔴 Бот отключен"
    bot.send_message(message.chat.id, f"Статус: {status}", reply_markup=get_menu_keyboard(message.from_user.id))

@bot.message_handler(func=lambda message: message.text == "👑 Админ-панель")
def admin_panel_text(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Доступ запрещен", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    bot.send_message(
        message.chat.id,
        "👑 Админ-панель",
        reply_markup=admin_panel_keyboard()
    )
    bot.send_message(
        message.chat.id,
        "🔙 Нажмите 'Назад' для возврата",
        reply_markup=back_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "📋 Заявки на продажу")
def admin_sell_requests_text(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Доступ запрещен", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    admin_sell_requests_message(message)

@bot.message_handler(func=lambda message: message.text == "📋 Заявки на покупку")
def admin_orders_text(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Доступ запрещен", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    admin_orders_list_message(message)

@bot.message_handler(func=lambda message: message.text == "🔄 Онлайн/Оффлайн")
def toggle_online_text(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ Доступ запрещен", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    global bot_online
    bot_online = not bot_online
    status = "🟢 Включен" if bot_online else "🔴 Выключен"
    bot.send_message(
        message.chat.id,
        f"🔄 Режим бота: {status}",
        reply_markup=get_menu_keyboard(message.from_user.id)
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    user_id = call.from_user.id
    global bot_online, order_counter

    if data == "admin_panel":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        bot.edit_message_text(
            "👑 Админ-панель",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=admin_panel_keyboard()
        )
        bot.send_message(
            call.message.chat.id,
            "🔙 Нажмите 'Назад' для возврата",
            reply_markup=back_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    if data == "check_online":
        status = "🟢 Бот работает" if bot_online else "🔴 Бот отключен"
        bot.answer_callback_query(call.id, status, show_alert=True)
        return

    if data == "toggle_online":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        bot_online = not bot_online
        status = "🟢 Включен" if bot_online else "🔴 Выключен"
        bot.answer_callback_query(call.id, f"🔄 Режим бота: {status}", show_alert=True)
        bot.edit_message_text(
            f"👑 Админ-панель\n\nСтатус бота: {status}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=admin_panel_keyboard()
        )
        bot.send_message(
            call.message.chat.id,
            "🔙 Нажмите 'Назад' для возврата",
            reply_markup=back_keyboard()
        )
        return

    if data == "search_menu":
        bot.edit_message_text(
            "🔍 Выберите тип поиска:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=search_keyboard()
        )
        bot.send_message(
            call.message.chat.id,
            "🔙 Нажмите 'Назад' для возврата",
            reply_markup=back_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    if data == "search_by_name":
        msg = bot.send_message(call.message.chat.id, "Введите название или часть названия аккаунта:")
        bot.register_next_step_handler(msg, search_name_result, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "search_by_trophies":
        msg = bot.send_message(call.message.chat.id, "Введите минимальное количество трофеев:")
        bot.register_next_step_handler(msg, search_trophies_result, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "search_by_price":
        msg = bot.send_message(call.message.chat.id, "Введите максимальную цену в ₴:")
        bot.register_next_step_handler(msg, search_price_result, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "sell_account":
        sell_account_start(call)
        return

    if data == "admin_sell_requests":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        admin_sell_requests(call)
        return

    if data.startswith("sell_approve_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        sell_approve(call)
        return

    if data.startswith("sell_reject_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        sell_reject(call)
        return

    if data.startswith("sell_set_price_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        sell_set_price_start(call)
        return

    if data.startswith("pay_card_"):
        order_id = int(data.split("_")[2])
        pay_card(call, order_id)
        return

    if data.startswith("pay_stars_"):
        order_id = int(data.split("_")[2])
        pay_stars(call, order_id)
        return

    if data.startswith("cancel_order_"):
        order_id = int(data.split("_")[2])
        cancel_order(call, order_id)
        return

    if data.startswith("confirm_payment_"):
        order_id = int(data.split("_")[2])
        confirm_payment(call, order_id)
        return

    if data == "leave_review":
        leave_review_start(call)
        return

    if data.startswith("review_"):
        review_select_purchase(call)
        return

    if data == "show_shop":
        if not bot_online:
            bot.answer_callback_query(call.id, "🔴 Бот временно отключен", show_alert=True)
            return
        show_shop(call)
        return

    if data.startswith("buy_"):
        if not bot_online:
            bot.answer_callback_query(call.id, "🔴 Бот временно отключен", show_alert=True)
            return
        buy_account(call)
        return

    if data == "admin_orders":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        admin_orders_list(call)
        return

    if data.startswith("approve_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        approve_order(call)
        return

    if data.startswith("reject_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        reject_order(call)
        return

    if data == "my_profile":
        my_profile(call)
        return

    if data.startswith("withdraw_"):
        user_id_int = int(data.split("_")[1])
        if user_id_int != user_id:
            bot.answer_callback_query(call.id, "⛔ Ошибка!", show_alert=True)
            return
        withdraw_start(call)
        return

    if data == "admin_add":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        msg = bot.send_message(call.message.chat.id, "Введите название аккаунта:")
        bot.register_next_step_handler(msg, add_name, call.message.message_id)
        bot.answer_callback_query(call.id)
        return

    if data == "admin_list":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        admin_list(call)
        return

    if data == "admin_delete":
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        admin_delete_start(call)
        return

    if data.startswith("del_"):
        if not is_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ Доступ запрещен", show_alert=True)
            return
        admin_delete_confirm(call)
        return

def show_shop_text(message):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, trophies, brawlers, price_uah, media FROM accounts WHERE sold = 0 AND reserved = 0 LIMIT 10")
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.send_message(message.chat.id, "😔 Аккаунтов в наличии нет.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    for acc in accounts:
        acc_id, name, trophies, brawlers, price_uah, media_str = acc
        text = account_card(acc_id, name, trophies, brawlers, price_uah, False)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("✅ Купить", callback_data=f"buy_{acc_id}"))
        send_media_group(message.chat.id, media_str, text, keyboard)
    bot.send_message(message.chat.id, "🛒 Конец витрины.", reply_markup=get_menu_keyboard(message.from_user.id))

def search_name_result(message, original_msg_id):
    if not bot_online:
        bot.send_message(message.chat.id, "🔴 Бот временно отключен.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    query = f"%{message.text}%"
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, trophies, brawlers, price_uah, media
        FROM accounts WHERE name LIKE ? AND sold = 0 AND reserved = 0
        LIMIT 10
    """, (query,))
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.send_message(message.chat.id, "😔 Ничего не найдено.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    for acc in accounts:
        acc_id, name, trophies, brawlers, price_uah, media_str = acc
        text = account_card(acc_id, name, trophies, brawlers, price_uah, False)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("✅ Купить", callback_data=f"buy_{acc_id}"))
        send_media_group(message.chat.id, media_str, text, keyboard)
    bot.send_message(message.chat.id, "🔍 Поиск завершён.", reply_markup=get_menu_keyboard(message.from_user.id))

def search_trophies_result(message, original_msg_id):
    if not bot_online:
        bot.send_message(message.chat.id, "🔴 Бот временно отключен.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число!", reply_markup=back_keyboard())
        return
    min_trophies = int(message.text)
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, trophies, brawlers, price_uah, media
        FROM accounts WHERE trophies >= ? AND sold = 0 AND reserved = 0
        LIMIT 10
    """, (min_trophies,))
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.send_message(message.chat.id, f"😔 Аккаунтов с {min_trophies}+ трофеями нет.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    for acc in accounts:
        acc_id, name, trophies, brawlers, price_uah, media_str = acc
        text = account_card(acc_id, name, trophies, brawlers, price_uah, False)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("✅ Купить", callback_data=f"buy_{acc_id}"))
        send_media_group(message.chat.id, media_str, text, keyboard)
    bot.send_message(message.chat.id, "🔍 Поиск завершён.", reply_markup=get_menu_keyboard(message.from_user.id))

def search_price_result(message, original_msg_id):
    if not bot_online:
        bot.send_message(message.chat.id, "🔴 Бот временно отключен.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число!", reply_markup=back_keyboard())
        return
    max_price = int(message.text)
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name, trophies, brawlers, price_uah, media
        FROM accounts WHERE price_uah <= ? AND sold = 0 AND reserved = 0
        LIMIT 10
    """, (max_price,))
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.send_message(message.chat.id, f"😔 Аккаунтов дешевле {max_price} ₴ нет.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    for acc in accounts:
        acc_id, name, trophies, brawlers, price_uah, media_str = acc
        text = account_card(acc_id, name, trophies, brawlers, price_uah, False)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("✅ Купить", callback_data=f"buy_{acc_id}"))
        send_media_group(message.chat.id, media_str, text, keyboard)
    bot.send_message(message.chat.id, "🔍 Поиск завершён.", reply_markup=get_menu_keyboard(message.from_user.id))

def show_shop(call):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, trophies, brawlers, price_uah, media FROM accounts WHERE sold = 0 AND reserved = 0 LIMIT 10")
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.edit_message_text(
            "😔 Аккаунтов в наличии нет.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
        return
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    for acc in accounts:
        acc_id, name, trophies, brawlers, price_uah, media_str = acc
        text = account_card(acc_id, name, trophies, brawlers, price_uah, False)
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("✅ Купить", callback_data=f"buy_{acc_id}"))
        send_media_group(call.message.chat.id, media_str, text, keyboard)
    bot.send_message(call.message.chat.id, "🛒 Конец витрины.", reply_markup=get_menu_keyboard(call.from_user.id))
    bot.answer_callback_query(call.id)

def sell_account_start(call):
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    text = (
        "📤 <b>Продажа аккаунта</b>\n\n"
        "Для продажи аккаунта свяжитесь с нашей поддержкой:\n"
        "<b>@poderzkabs</b>\n\n"
        "📌 Напишите им с пометкой <b>\"ПРОДАЖА АККАУНТА\"</b>\n"
        "и укажите:\n"
        "• Название аккаунта\n"
        "• Трофеи\n"
        "• Бравлеры\n"
        "• Вашу цену в ₴ или ⭐\n"
        "• Скриншоты/видео\n\n"
        "✅ Наши менеджеры свяжутся с вами в ближайшее время!"
    )
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📩 Написать поддержке", url="https://t.me/poderzkabs"),
    )
    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    bot.send_message(call.message.chat.id, "🔙 Вернуться в меню", reply_markup=get_menu_keyboard(call.from_user.id))
    bot.answer_callback_query(call.id)

def sell_account_text(message):
    text = (
        "📤 <b>Продажа аккаунта</b>\n\n"
        "Для продажи аккаунта свяжитесь с нашей поддержкой:\n"
        "<b>@poderzkabs</b>\n\n"
        "📌 Напишите им с пометкой <b>\"ПРОДАЖА АККАУНТА\"</b>\n"
        "и укажите:\n"
        "• Название аккаунта\n"
        "• Трофеи\n"
        "• Бравлеры\n"
        "• Вашу цену в ₴ или ⭐\n"
        "• Скриншоты/видео\n\n"
        "✅ Наши менеджеры свяжутся с вами в ближайшее время!"
    )
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📩 Написать поддержке", url="https://t.me/poderzkabs"),
    )
    bot.send_message(
        message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    bot.send_message(message.chat.id, "🔙 Вернуться в меню", reply_markup=get_menu_keyboard(message.from_user.id))

def admin_sell_requests_message(message):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, user_id, status FROM sell_requests WHERE status = 'pending'")
    requests = cur.fetchall()
    conn.close()
    if not requests:
        bot.send_message(message.chat.id, "📋 Нет активных заявок на продажу.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    text = "📤 <b>ЗАЯВКИ НА ПРОДАЖУ:</b>\n\n"
    for req_id, name, price, user_id, status in requests:
        text += f"📋 #{req_id}\n"
        text += f"🏆 {name} — {price} ₴\n"
        text += f"👤 Продавец: {user_id}\n\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=get_menu_keyboard(message.from_user.id))

def admin_sell_requests(call):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, price, user_id, status FROM sell_requests WHERE status = 'pending'")
    requests = cur.fetchall()
    conn.close()
    if not requests:
        bot.edit_message_text(
            "📋 Нет активных заявок на продажу.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=admin_panel_keyboard()
        )
        bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
        return
    text = "📤 <b>ЗАЯВКИ НА ПРОДАЖУ:</b>\n\n"
    for req_id, name, price, user_id, status in requests:
        text += f"📋 #{req_id}\n"
        text += f"🏆 {name} — {price} ₴\n"
        text += f"👤 Продавец: {user_id}\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔄 Обновить", callback_data="admin_sell_requests"),
    )
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    bot.send_message(call.message.chat.id, "🔙 Вернуться", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def sell_approve(call):
    request_id = int(call.data.split("_")[2])
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id, name, trophies, brawlers, price, media, login, password, email
        FROM sell_requests WHERE id = ?
    """, (request_id,))
    result = cur.fetchone()
    if not result:
        bot.answer_callback_query(call.id, "❌ Заявка не найдена!", show_alert=True)
        conn.close()
        return
    user_id, name, trophies, brawlers, price, media, login, password, email = result
    cur.execute("SELECT admin_price FROM sell_requests WHERE id = ?", (request_id,))
    admin_price_result = cur.fetchone()
    admin_price = admin_price_result[0] if admin_price_result and admin_price_result[0] else int(price * 1.4)
    cur.execute("""
        INSERT INTO accounts (name, trophies, brawlers, price_uah, media, login, password, email, seller_id, seller_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (name, trophies, brawlers, admin_price, media, login, password, email, user_id, price))
    cur.execute("UPDATE sell_requests SET status = 'approved' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()
    price_stars = int(admin_price * UAH_TO_STARS)
    try:
        bot.send_message(
            user_id,
            f"✅ Ваш аккаунт <b>{name}</b> одобрен и добавлен в витрину!\n"
            f"💰 Ваша цена: {price} ₴\n"
            f"🏷️ Цена в магазине: {admin_price} ₴ / {price_stars} ⭐\n\n"
            f"При продаже вы получите {100 - COMMISSION_PERCENT}% от вашей цены.",
            parse_mode='HTML'
        )
    except:
        pass
    bot.edit_message_text(
        f"✅ Заявка #{request_id} одобрена!\nАккаунт добавлен в витрину по цене {admin_price} ₴ / {price_stars} ⭐.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id, "✅ Заявка одобрена")

def sell_reject(call):
    request_id = int(call.data.split("_")[2])
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id, name, media FROM sell_requests WHERE id = ?", (request_id,))
    result = cur.fetchone()
    if not result:
        bot.answer_callback_query(call.id, "❌ Заявка не найдена!", show_alert=True)
        conn.close()
        return
    user_id, name, media = result
    if media:
        for path in media.split("|||"):
            if os.path.exists(path):
                os.remove(path)
    cur.execute("UPDATE sell_requests SET status = 'rejected' WHERE id = ?", (request_id,))
    conn.commit()
    conn.close()
    try:
        bot.send_message(
            user_id,
            f"❌ Ваш аккаунт <b>{name}</b> отклонён администрацией.",
            parse_mode='HTML'
        )
    except:
        pass
    bot.edit_message_text(
        f"❌ Заявка #{request_id} отклонена.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id, "❌ Заявка отклонена")

def sell_set_price_start(call):
    request_id = int(call.data.split("_")[2])
    msg = bot.send_message(
        call.message.chat.id,
        "💰 Введите новую цену для аккаунта (в ₴):"
    )
    bot.register_next_step_handler(msg, sell_set_price, request_id, call.message.message_id)
    bot.answer_callback_query(call.id)

def sell_set_price(message, request_id, original_msg_id):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "❌ Введите число!", reply_markup=back_keyboard())
        msg = bot.send_message(message.chat.id, "Введите цену (в ₴):")
        bot.register_next_step_handler(msg, sell_set_price, request_id, original_msg_id)
        return
    admin_price = int(message.text)
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE sell_requests SET admin_price = ? WHERE id = ?", (admin_price, request_id))
    conn.commit()
    conn.close()
    bot.edit_message_text(
        f"✅ Цена для заявки #{request_id} установлена: {admin_price} ₴\nТеперь одобрите заявку.",
        chat_id=message.chat.id,
        message_id=original_msg_id
    )
    bot.send_message(message.chat.id, "🔙 Назад", reply_markup=back_keyboard())

def buy_account(call):
    global order_counter
    acc_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT sold, reserved, name, price_uah, login, password, email, seller_id, seller_price FROM accounts WHERE id = ?", (acc_id,))
    result = cur.fetchone()
    if not result:
        bot.answer_callback_query(call.id, "❌ Аккаунт не найден!", show_alert=True)
        conn.close()
        return
    sold, reserved, name, price_uah, login, password, email, seller_id, seller_price = result
    if sold == 1:
        bot.answer_callback_query(call.id, "❌ Аккаунт уже продан!", show_alert=True)
        conn.close()
        return
    if reserved == 1:
        bot.answer_callback_query(call.id, "⏳ Аккаунт уже забронирован!", show_alert=True)
        conn.close()
        return
    cur.execute("UPDATE accounts SET reserved = 1 WHERE id = ?", (acc_id,))
    cur.execute("""
        INSERT INTO purchases (user_id, account_id, status) VALUES (?, ?, 'pending_payment')
    """, (user_id, acc_id))
    purchase_id = cur.lastrowid
    conn.commit()
    conn.close()
    order_id = order_counter
    order_counter += 1
    price_stars = int(price_uah * UAH_TO_STARS)
    account_data = {
        "id": acc_id,
        "name": name,
        "price_uah": price_uah,
        "price_stars": price_stars,
        "login": login,
        "password": password,
        "email": email,
        "seller_id": seller_id,
        "seller_price": seller_price
    }
    pending_orders[order_id] = {
        "user_id": user_id,
        "account_id": acc_id,
        "purchase_id": purchase_id,
        "account_data": account_data,
        "status": "pending_payment"
    }
    text = (
        f"🛒 Вы выбрали аккаунт:\n\n"
        f"🏆 {name}\n"
        f"💰 Цена: {price_uah} ₴ / {price_stars} ⭐\n\n"
        f"Выберите способ оплаты:"
    )
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(
        call.message.chat.id,
        text,
        reply_markup=payment_keyboard(name, price_uah, price_stars, order_id)
    )
    bot.send_message(call.message.chat.id, "🔙 Отменить заказ", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def pay_card(call, order_id):
    if order_id not in pending_orders:
        bot.answer_callback_query(call.id, "❌ Заказ не найден!", show_alert=True)
        return
    order = pending_orders[order_id]
    account_name = order["account_data"]["name"]
    price_uah = order["account_data"]["price_uah"]
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET payment_method = 'card', currency = 'UAH', amount = ? WHERE id = ?",
                (price_uah, order["purchase_id"]))
    conn.commit()
    conn.close()
    text = (
        f"💳 <b>Оплата картой (Гривна)</b>\n\n"
        f"🏆 Аккаунт: {account_name}\n"
        f"💰 Сумма: {price_uah} ₴\n\n"
        f"📋 <b>Реквизиты для оплаты:</b>\n"
        f"<b>Номер карты:</b>\n<code>{CARD_NUMBER}</code>\n\n"
        f"💳 <b>Получатель:</b> по запросу\n"
        f"🏦 <b>Банк:</b> OTP Bank\n\n"
        f"📌 <b>Инструкция:</b>\n"
        f"• Введите сумму <b>{price_uah} ₴</b>\n"
        f"• В комментарии укажите: <code>#{order_id}</code>\n"
        f"• <b>После оплаты</b> нажмите кнопку <b>\"✅ Я оплатил\"</b>\n\n"
        f"⚠️ <b>ВАЖНО!</b>\n"
        f"Без комментария #{order_id} мы не сможем идентифицировать платёж!"
    )
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✅ Я оплатил", callback_data=f"confirm_payment_{order_id}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_order_{order_id}")
    )
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    bot.send_message(call.message.chat.id, "🔙 Отменить", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def pay_stars(call, order_id):
    if order_id not in pending_orders:
        bot.answer_callback_query(call.id, "❌ Заказ не найден!", show_alert=True)
        return
    order = pending_orders[order_id]
    account_name = order["account_data"]["name"]
    price_stars = order["account_data"]["price_stars"]
    price_uah = order["account_data"]["price_uah"]
    user_id = call.from_user.id
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET payment_method = 'stars', currency = 'STARS', amount = ? WHERE id = ?",
                (price_stars, order["purchase_id"]))
    conn.commit()
    conn.close()
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    success = send_gift(user_id, price_stars)
    if not success:
        bot.send_message(
            call.message.chat.id,
            "❌ Не удалось отправить подарок. Попробуйте позже.",
            reply_markup=get_menu_keyboard(user_id)
        )
        bot.answer_callback_query(call.id, "❌ Ошибка")
        return
    text = (
        f"⭐ <b>Оплата звёздами через подарок</b>\n\n"
        f"🏆 Аккаунт: {account_name}\n"
        f"💰 Сумма: {price_uah} ₴ → {price_stars} ⭐\n"
        f"📊 Курс: 1 ₴ = {UAH_TO_STARS} ⭐\n\n"
        f"📌 <b>Инструкция:</b>\n"
        f"1️⃣ Вам отправлен <b>подарок</b> на {price_stars} ⭐\n"
        f"2️⃣ Нажмите на подарок и выберите <b>\"Переслать\"</b>\n"
        f"3️⃣ Отправьте его на <b>@aironqq</b>\n"
        f"4️⃣ После пересылки нажмите кнопку <b>\"✅ Я переслал\"</b>\n\n"
        f"⚠️ <b>ВНИМАНИЕ!</b>\n"
        f"• Подарок нужно переслать <b>целиком</b>, не распаковывая\n"
        f"• Без пересылки подарка оплата не будет подтверждена"
    )
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✅ Я переслал", callback_data=f"confirm_payment_{order_id}"),
        InlineKeyboardButton("❌ Отменить", callback_data=f"cancel_order_{order_id}")
    )
    bot.send_message(
        call.message.chat.id,
        text,
        parse_mode='HTML',
        reply_markup=keyboard
    )
    bot.send_message(call.message.chat.id, "🔙 Отменить", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id, "🎁 Подарок отправлен!")

def cancel_order(call, order_id):
    if order_id not in pending_orders:
        bot.answer_callback_query(call.id, "❌ Заказ не найден!", show_alert=True)
        return
    order = pending_orders[order_id]
    account_id = order["account_id"]
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET reserved = 0 WHERE id = ?", (account_id,))
    cur.execute("UPDATE purchases SET status = 'cancelled' WHERE id = ?", (order["purchase_id"],))
    conn.commit()
    conn.close()
    del pending_orders[order_id]
    bot.edit_message_text(
        "❌ Заказ отменён. Аккаунт снова доступен.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 В меню", reply_markup=get_menu_keyboard(call.from_user.id))
    bot.answer_callback_query(call.id, "❌ Заказ отменён")

def confirm_payment(call, order_id):
    user_id = call.from_user.id
    if order_id not in pending_orders:
        bot.answer_callback_query(call.id, "❌ Заказ не найден!", show_alert=True)
        return
    order = pending_orders[order_id]
    account_data = order["account_data"]
    payment_method = "картой (₴)" if order.get("payment_method") == "card" else "звёздами (⭐)"
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET status = 'pending' WHERE id = ?", (order["purchase_id"],))
    conn.commit()
    conn.close()
    order_text = (
        f"📋 НОВАЯ ЗАЯВКА НА ПОКУПКУ!\n\n"
        f"📋 Заявка #{order_id}\n"
        f"👤 Покупатель: {user_id}\n"
        f"🏆 Аккаунт: {account_data['name']}\n"
        f"💰 Цена: {account_data['price_uah']} ₴ / {account_data['price_stars']} ⭐\n"
        f"💳 Оплата: {payment_method}\n\n"
        f"✅ Пользователь подтвердил оплату!\n"
        f"Проверьте и подтвердите выдачу."
    )
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Выдать аккаунт", callback_data=f"approve_{order_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{order_id}")
    )
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, order_text, reply_markup=keyboard)
        except:
            pass
    bot.edit_message_text(
        f"✅ Оплата подтверждена!\n\n"
        f"📋 Заявка #{order_id} отправлена администратору.\n"
        f"⏳ Ожидайте выдачи аккаунта.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 В меню", reply_markup=get_menu_keyboard(call.from_user.id))
    bot.answer_callback_query(call.id, "✅ Оплата подтверждена")

def approve_order(call):
    order_id = int(call.data.split("_")[1])
    if order_id not in pending_orders:
        bot.answer_callback_query(call.id, "❌ Заявка уже обработана!", show_alert=True)
        return
    order = pending_orders[order_id]
    user_id = order["user_id"]
    account_id = order["account_id"]
    purchase_id = order["purchase_id"]
    account_data = order["account_data"]
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET sold = 1, reserved = 0 WHERE id = ?", (account_id,))
    cur.execute("UPDATE purchases SET status = 'approved' WHERE id = ?", (purchase_id,))
    seller_id = account_data.get("seller_id")
    seller_price = account_data.get("seller_price")
    if seller_id and seller_price:
        commission = int(seller_price * COMMISSION_PERCENT / 100)
        seller_payout = seller_price - commission
        add_balance(seller_id, seller_payout)
        cur.execute("""
            INSERT INTO users (user_id, total_sold) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET total_sold = total_sold + ?
        """, (seller_id, seller_price, seller_price))
    conn.commit()
    conn.close()
    data_text = (
        f"🎉 Поздравляем с покупкой!\n\n"
        f"🏆 Аккаунт: {account_data['name']}\n"
        f"💰 Цена: {account_data['price_uah']} ₴ / {account_data['price_stars']} ⭐\n\n"
        f"🔑 Логин: {account_data['login']}\n"
        f"🔒 Пароль: {account_data['password']}\n"
        f"📧 Почта: {account_data['email'] or 'не указана'}\n\n"
        f"⚠️ Смените пароль при первом входе!\n"
        f"📋 Заявка #{order_id} одобрена.\n\n"
        f"⭐ Не забудьте оставить отзыв о покупке!"
    )
    try:
        bot.send_message(user_id, data_text)
    except:
        pass
    if seller_id and seller_price:
        commission = int(seller_price * COMMISSION_PERCENT / 100)
        seller_payout = seller_price - commission
        try:
            bot.send_message(
                seller_id,
                f"🎉 Ваш аккаунт <b>{account_data['name']}</b> был продан!\n\n"
                f"💰 Ваша цена: {seller_price} ₴\n"
                f"📊 Комиссия бота ({COMMISSION_PERCENT}%): {commission} ₴\n"
                f"✅ Вы получили: {seller_payout} ₴\n\n"
                f"💰 Ваш баланс: {get_balance(seller_id)} ₴",
                parse_mode='HTML'
            )
        except:
            pass
    del pending_orders[order_id]
    bot.edit_message_text(
        f"✅ Заявка #{order_id} одобрена! Данные отправлены пользователю.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 В меню", reply_markup=get_menu_keyboard(call.from_user.id))
    bot.answer_callback_query(call.id, "✅ Заявка одобрена")

def reject_order(call):
    order_id = int(call.data.split("_")[1])
    if order_id not in pending_orders:
        bot.answer_callback_query(call.id, "❌ Заявка уже обработана!", show_alert=True)
        return
    order = pending_orders[order_id]
    user_id = order["user_id"]
    account_id = order["account_id"]
    purchase_id = order["purchase_id"]
    account_data = order["account_data"]
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE accounts SET reserved = 0 WHERE id = ?", (account_id,))
    cur.execute("UPDATE purchases SET status = 'rejected' WHERE id = ?", (purchase_id,))
    conn.commit()
    conn.close()
    try:
        bot.send_message(
            user_id,
            f"❌ Заявка #{order_id} на покупку аккаунта '{account_data['name']}' отклонена."
        )
    except:
        pass
    del pending_orders[order_id]
    bot.edit_message_text(
        f"❌ Заявка #{order_id} отклонена. Аккаунт снова доступен.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 В меню", reply_markup=get_menu_keyboard(call.from_user.id))
    bot.answer_callback_query(call.id, "❌ Заявка отклонена")

def admin_orders_list_message(message):
    if not pending_orders:
        bot.send_message(message.chat.id, "📋 Активных заявок на покупку нет.", reply_markup=get_menu_keyboard(message.from_user.id))
        return
    text = "📋 Активные заявки на покупку:\n\n"
    for order_id, order in pending_orders.items():
        status_text = "⏳ Ожидает оплаты" if order.get("status") == "pending_payment" else "⏳ Ожидает выдачи"
        text += f"#{order_id} — {order['account_data']['name']}\n"
        text += f"💰 {order['account_data']['price_uah']} ₴ / {order['account_data']['price_stars']} ⭐\n"
        text += f"👤 Покупатель: {order['user_id']}\n"
        text += f"📌 {status_text}\n\n"
    bot.send_message(message.chat.id, text, reply_markup=get_menu_keyboard(message.from_user.id))

def admin_orders_list(call):
    if not pending_orders:
        bot.edit_message_text(
            "📋 Активных заявок на покупку нет.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=admin_panel_keyboard()
        )
        bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
        return
    text = "📋 Активные заявки на покупку:\n\n"
    for order_id, order in pending_orders.items():
        status_text = "⏳ Ожидает оплаты" if order.get("status") == "pending_payment" else "⏳ Ожидает выдачи"
        text += f"#{order_id} — {order['account_data']['name']}\n"
        text += f"💰 {order['account_data']['price_uah']} ₴ / {order['account_data']['price_stars']} ⭐\n"
        text += f"👤 Покупатель: {order['user_id']}\n"
        text += f"📌 {status_text}\n\n"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🔄 Обновить", callback_data="admin_orders"),
    )
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )
    bot.send_message(call.message.chat.id, "🔙 Вернуться", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def leave_review_start(call):
    user_id = call.from_user.id
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, a.name
        FROM purchases p
        JOIN accounts a ON p.account_id = a.id
        WHERE p.user_id = ? AND p.status = 'approved'
        AND p.review IS NULL
        ORDER BY p.purchase_date DESC
        LIMIT 5
    """, (user_id,))
    purchases = cur.fetchall()
    conn.close()
    if not purchases:
        bot.answer_callback_query(call.id, "❌ У вас нет покупок для отзыва!", show_alert=True)
        return
    if len(purchases) == 1:
        purchase_id, account_name = purchases[0]
        pending_reviews[user_id] = {"purchase_id": purchase_id, "account_name": account_name}
        bot.edit_message_text(
            f"⭐ Оставьте отзыв о покупке аккаунта:\n\n🏆 {account_name}\n\nНапишите текст отзыва (можно отправить фото или видео):",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.send_message(call.message.chat.id, "🔙 Отмена", reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    for pid, name in purchases:
        keyboard.add(InlineKeyboardButton(f"🏆 {name}", callback_data=f"review_{pid}"))
    bot.edit_message_text(
        "Выберите аккаунт, о котором хотите оставить отзыв:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )
    bot.send_message(call.message.chat.id, "🔙 Отмена", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def review_select_purchase(call):
    purchase_id = int(call.data.split("_")[1])
    user_id = call.from_user.id
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT a.name
        FROM purchases p
        JOIN accounts a ON p.account_id = a.id
        WHERE p.id = ? AND p.user_id = ?
    """, (purchase_id, user_id))
    result = cur.fetchone()
    conn.close()
    if not result:
        bot.answer_callback_query(call.id, "❌ Ошибка!", show_alert=True)
        return
    account_name = result[0]
    pending_reviews[user_id] = {"purchase_id": purchase_id, "account_name": account_name}
    bot.edit_message_text(
        f"⭐ Оставьте отзыв о покупке аккаунта:\n\n🏆 {account_name}\n\nНапишите текст отзыва (можно отправить фото или видео):",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 Отмена", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda message: message.from_user.id in pending_reviews and message.text and message.text != "🔙 Назад")
def handle_review_text(message):
    user_id = message.from_user.id
    review_data = pending_reviews[user_id]
    purchase_id = review_data["purchase_id"]
    account_name = review_data["account_name"]
    review_text = message.text
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET review = ? WHERE id = ?", (review_text, purchase_id))
    cur.execute("INSERT INTO reviews (user_id, purchase_id, text) VALUES (?, ?, ?)",
                (user_id, purchase_id, review_text))
    conn.commit()
    conn.close()
    try:
        channel_message = (
            f"⭐ НОВЫЙ ОТЗЫВ!\n\n"
            f"🏆 Аккаунт: {account_name}\n"
            f"💬 {review_text}\n\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        bot.send_message(CHANNEL_ID, channel_message)
    except Exception as e:
        print(f"Ошибка отправки в канал: {e}")
        bot.send_message(message.chat.id, "⚠️ Не удалось опубликовать отзыв в канале, но он сохранён!")
    del pending_reviews[user_id]
    bot.send_message(
        message.chat.id,
        "✅ Спасибо за отзыв! Он будет опубликован в нашем канале.",
        reply_markup=get_menu_keyboard(user_id)
    )

@bot.message_handler(func=lambda message: message.from_user.id in pending_reviews and message.photo)
def handle_review_photo(message):
    user_id = message.from_user.id
    review_data = pending_reviews[user_id]
    purchase_id = review_data["purchase_id"]
    account_name = review_data["account_name"]
    photo_id = message.photo[-1].file_id
    caption = message.caption or "Фото-отзыв"
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET review = ?, review_media = ? WHERE id = ?",
                (caption, photo_id, purchase_id))
    cur.execute("INSERT INTO reviews (user_id, purchase_id, text, media_file_id, media_type) VALUES (?, ?, ?, ?, ?)",
                (user_id, purchase_id, caption, photo_id, "photo"))
    conn.commit()
    conn.close()
    try:
        channel_text = (
            f"⭐ НОВЫЙ ОТЗЫВ!\n\n"
            f"🏆 Аккаунт: {account_name}\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        bot.send_photo(CHANNEL_ID, photo_id, caption=channel_text)
    except Exception as e:
        print(f"Ошибка отправки в канал: {e}")
        bot.send_message(message.chat.id, "⚠️ Не удалось опубликовать отзыв в канале, но он сохранён!")
    del pending_reviews[user_id]
    bot.send_message(
        message.chat.id,
        "✅ Спасибо за отзыв! Он будет опубликован в нашем канале.",
        reply_markup=get_menu_keyboard(user_id)
    )

@bot.message_handler(func=lambda message: message.from_user.id in pending_reviews and message.video)
def handle_review_video(message):
    user_id = message.from_user.id
    review_data = pending_reviews[user_id]
    purchase_id = review_data["purchase_id"]
    account_name = review_data["account_name"]
    video_id = message.video.file_id
    caption = message.caption or "Видео-отзыв"
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE purchases SET review = ?, review_media = ? WHERE id = ?",
                (caption, video_id, purchase_id))
    cur.execute("INSERT INTO reviews (user_id, purchase_id, text, media_file_id, media_type) VALUES (?, ?, ?, ?, ?)",
                (user_id, purchase_id, caption, video_id, "video"))
    conn.commit()
    conn.close()
    try:
        channel_text = (
            f"⭐ НОВЫЙ ОТЗЫВ!\n\n"
            f"🏆 Аккаунт: {account_name}\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )
        bot.send_video(CHANNEL_ID, video_id, caption=channel_text)
    except Exception as e:
        print(f"Ошибка отправки в канал: {e}")
        bot.send_message(message.chat.id, "⚠️ Не удалось опубликовать отзыв в канале, но он сохранён!")
    del pending_reviews[user_id]
    bot.send_message(
        message.chat.id,
        "✅ Спасибо за отзыв! Он будет опубликован в нашем канале.",
        reply_markup=get_menu_keyboard(user_id)
    )

def my_profile_text(message):
    user_id = message.from_user.id
    balance = get_balance(user_id)
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ? AND status = 'approved'", (user_id,))
    total_purchases = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reviews WHERE user_id = ?", (user_id,))
    total_reviews = cur.fetchone()[0]
    cur.execute("SELECT total_sold FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    total_sold = result[0] if result else 0
    cur.execute("""
        SELECT a.name, a.price_uah, p.purchase_date, p.status, p.currency, p.amount
        FROM purchases p
        JOIN accounts a ON p.account_id = a.id
        WHERE p.user_id = ?
        ORDER BY p.purchase_date DESC
        LIMIT 10
    """, (user_id,))
    history = cur.fetchall()
    conn.close()
    text = f"👤 <b>Ваш профиль</b>\n\n"
    text += f"💰 Баланс: {balance} ₴\n"
    text += f"📦 Куплено: {total_purchases}\n"
    text += f"📤 Продано на: {total_sold} ₴\n"
    text += f"⭐ Отзывов: {total_reviews}\n\n"
    if history:
        text += "📋 История:\n"
        for name, price, date, status, currency, amount in history:
            date_str = datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
            status_emoji = "✅" if status == "approved" else "❌" if status == "rejected" else "⏳"
            currency_icon = "⭐" if currency == "STARS" else "₴"
            text += f"• {name} — {amount} {currency_icon} {status_emoji} ({date_str})\n"
    else:
        text += "У вас пока нет покупок."
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = [
        InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review"),
        InlineKeyboardButton("📢 Смотреть отзывы", url=CHANNEL_LINK),
    ]
    if balance > 0:
        buttons.append(InlineKeyboardButton("💳 Вывести средства", callback_data=f"withdraw_{user_id}"))
    keyboard.add(*buttons)
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    bot.send_message(message.chat.id, "🔙 Назад", reply_markup=get_menu_keyboard(user_id))

def my_profile(call):
    user_id = call.from_user.id
    balance = get_balance(user_id)
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM purchases WHERE user_id = ? AND status = 'approved'", (user_id,))
    total_purchases = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reviews WHERE user_id = ?", (user_id,))
    total_reviews = cur.fetchone()[0]
    cur.execute("SELECT total_sold FROM users WHERE user_id = ?", (user_id,))
    result = cur.fetchone()
    total_sold = result[0] if result else 0
    cur.execute("""
        SELECT a.name, a.price_uah, p.purchase_date, p.status, p.currency, p.amount
        FROM purchases p
        JOIN accounts a ON p.account_id = a.id
        WHERE p.user_id = ?
        ORDER BY p.purchase_date DESC
        LIMIT 10
    """, (user_id,))
    history = cur.fetchall()
    conn.close()
    text = f"👤 <b>Ваш профиль</b>\n\n"
    text += f"💰 Баланс: {balance} ₴\n"
    text += f"📦 Куплено: {total_purchases}\n"
    text += f"📤 Продано на: {total_sold} ₴\n"
    text += f"⭐ Отзывов: {total_reviews}\n\n"
    if history:
        text += "📋 История:\n"
        for name, price, date, status, currency, amount in history:
            date_str = datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
            status_emoji = "✅" if status == "approved" else "❌" if status == "rejected" else "⏳"
            currency_icon = "⭐" if currency == "STARS" else "₴"
            text += f"• {name} — {amount} {currency_icon} {status_emoji} ({date_str})\n"
    else:
        text += "У вас пока нет покупок."
    keyboard = InlineKeyboardMarkup(row_width=1)
    buttons = [
        InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review"),
        InlineKeyboardButton("📢 Смотреть отзывы", url=CHANNEL_LINK),
    ]
    if balance > 0:
        buttons.append(InlineKeyboardButton("💳 Вывести средства", callback_data=f"withdraw_{user_id}"))
    keyboard.add(*buttons)
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=get_menu_keyboard(user_id))
    bot.answer_callback_query(call.id)

def withdraw_start(call):
    user_id = call.from_user.id
    balance = get_balance(user_id)
    if balance <= 0:
        bot.answer_callback_query(call.id, "❌ У вас нет средств для вывода!", show_alert=True)
        return
    bot.edit_message_text(
        f"💳 <b>Вывод средств</b>\n\n"
        f"💰 Ваш баланс: {balance} ₴\n\n"
        f"Введите сумму для вывода (или 'все' для полного вывода):\n"
        f"Минимальная сумма: 100 ₴",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    msg = bot.send_message(call.message.chat.id, "Введите сумму:")
    bot.register_next_step_handler(msg, withdraw_amount, user_id)
    bot.answer_callback_query(call.id)

def withdraw_amount(message, user_id):
    balance = get_balance(user_id)
    if message.text.lower() == "все":
        amount = balance
    else:
        if not message.text.isdigit():
            bot.send_message(message.chat.id, "❌ Введите число!", reply_markup=back_keyboard())
            msg = bot.send_message(message.chat.id, "Введите сумму для вывода:")
            bot.register_next_step_handler(msg, withdraw_amount, user_id)
            return
        amount = int(message.text)
    if amount < 100:
        bot.send_message(message.chat.id, "❌ Минимальная сумма вывода: 100 ₴", reply_markup=get_menu_keyboard(user_id))
        return
    if amount > balance:
        bot.send_message(message.chat.id, f"❌ У вас недостаточно средств! Доступно: {balance} ₴", reply_markup=get_menu_keyboard(user_id))
        return
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"💳 <b>ЗАПРОС НА ВЫВОД</b>\n\n"
                f"👤 Пользователь: {user_id}\n"
                f"💰 Сумма: {amount} ₴\n\n"
                f"Выплатите пользователю и подтвердите.",
                parse_mode='HTML'
            )
        except:
            pass
    bot.send_message(
        message.chat.id,
        f"✅ Заявка на вывод {amount} ₴ отправлена администрации!\n"
        f"⏳ Ожидайте выплату.",
        reply_markup=get_menu_keyboard(user_id)
    )

def add_name(message, original_msg_id):
    user_id = message.from_user.id
    add_data[user_id] = {"name": message.text}
    msg = bot.send_message(message.chat.id, "Введите количество трофеев (цифра):")
    bot.register_next_step_handler(msg, add_trophies, user_id, original_msg_id)

def add_trophies(message, user_id, original_msg_id):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число!", reply_markup=back_keyboard())
        msg = bot.send_message(message.chat.id, "Введите количество трофеев (цифра):")
        bot.register_next_step_handler(msg, add_trophies, user_id, original_msg_id)
        return
    add_data[user_id]['trophies'] = int(message.text)
    msg = bot.send_message(message.chat.id, "Введите количество бравлеров (цифра):")
    bot.register_next_step_handler(msg, add_brawlers, user_id, original_msg_id)

def add_brawlers(message, user_id, original_msg_id):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число!", reply_markup=back_keyboard())
        msg = bot.send_message(message.chat.id, "Введите количество бравлеров (цифра):")
        bot.register_next_step_handler(msg, add_brawlers, user_id, original_msg_id)
        return
    add_data[user_id]['brawlers'] = int(message.text)
    msg = bot.send_message(message.chat.id, "Введите цену в ₴ (цифра):")
    bot.register_next_step_handler(msg, add_price, user_id, original_msg_id)

def add_price(message, user_id, original_msg_id):
    if not message.text.isdigit():
        bot.send_message(message.chat.id, "Введите число!", reply_markup=back_keyboard())
        msg = bot.send_message(message.chat.id, "Введите цену в ₴ (цифра):")
        bot.register_next_step_handler(msg, add_price, user_id, original_msg_id)
        return
    add_data[user_id]['price'] = int(message.text)
    msg = bot.send_message(message.chat.id, "Введите логин (email или ID Supercell):")
    bot.register_next_step_handler(msg, add_login, user_id, original_msg_id)

def add_login(message, user_id, original_msg_id):
    add_data[user_id]['login'] = message.text
    msg = bot.send_message(message.chat.id, "Введите пароль:")
    bot.register_next_step_handler(msg, add_password, user_id, original_msg_id)

def add_password(message, user_id, original_msg_id):
    add_data[user_id]['password'] = message.text
    msg = bot.send_message(message.chat.id, "Введите почту (или 'нет'):")
    bot.register_next_step_handler(msg, add_email, user_id, original_msg_id)

def add_email(message, user_id, original_msg_id):
    add_data[user_id]['email'] = None if message.text.lower() == "нет" else message.text
    add_data[user_id]['media_files'] = []
    add_data[user_id]['media_count'] = 0
    msg = bot.send_message(
        message.chat.id,
        "📸 Отправьте медиафайлы для аккаунта:\n"
        "• Можно отправить <b>1 видео</b> или <b>до 4 фото</b>\n"
        "• После отправки всех файлов напишите <b>готово</b>\n"
        "• Если медиа не нужно, напишите <b>нет</b>",
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, add_media, user_id, original_msg_id)

def add_media(message, user_id, original_msg_id):
    if message.text and message.text.lower() in ["готово", "нет", "да"]:
        confirm_account(message, user_id, original_msg_id)
        return
    media_files = add_data[user_id].get('media_files', [])
    media_count = add_data[user_id].get('media_count', 0)
    if media_count >= 4:
        bot.send_message(message.chat.id, "⛔ Максимум 4 файла! Напишите 'готово' для завершения.", reply_markup=back_keyboard())
        return
    if message.photo:
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        temp_path = IMAGES_DIR / f"temp_{user_id}_{media_count}.jpg"
        downloaded_file = bot.download_file(file_info.file_path)
        with open(temp_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        media_files.append(str(temp_path))
        media_count += 1
        add_data[user_id]['media_files'] = media_files
        add_data[user_id]['media_count'] = media_count
        bot.send_message(
            message.chat.id,
            f"✅ Фото {media_count}/4 загружено!\n"
            f"Отправьте ещё или напишите 'готово'.",
            reply_markup=back_keyboard()
        )
        bot.register_next_step_handler(message, add_media, user_id, original_msg_id)
        return
    if message.video:
        video = message.video
        file_info = bot.get_file(video.file_id)
        temp_path = IMAGES_DIR / f"temp_{user_id}_video.mp4"
        downloaded_file = bot.download_file(file_info.file_path)
        with open(temp_path, 'wb') as new_file:
            new_file.write(downloaded_file)
        if media_files:
            for f in media_files:
                if os.path.exists(f):
                    os.remove(f)
            media_files = []
            bot.send_message(message.chat.id, "🔄 Фото удалены, добавлено видео.", reply_markup=back_keyboard())
        media_files.append(str(temp_path))
        add_data[user_id]['media_files'] = media_files
        add_data[user_id]['media_count'] = 1
        bot.send_message(
            message.chat.id,
            "✅ Видео загружено!\n"
            "Напишите 'готово' для продолжения.",
            reply_markup=back_keyboard()
        )
        bot.register_next_step_handler(message, add_media, user_id, original_msg_id)
        return
    msg = bot.send_message(
        message.chat.id,
        "❌ Отправьте фото или видео!\n"
        "Или напишите 'готово' для завершения.",
        reply_markup=back_keyboard()
    )
    bot.register_next_step_handler(msg, add_media, user_id, original_msg_id)

def confirm_account(message, user_id, original_msg_id):
    data = add_data.get(user_id, {})
    confirm_text = (
        f"📋 Проверьте данные:\n\n"
        f"Название: {data.get('name', '')}\n"
        f"Трофеи: {data.get('trophies', '')}\n"
        f"Бравлеры: {data.get('brawlers', '')}\n"
        f"Цена: {data.get('price', '')} ₴\n"
        f"Логин: {data.get('login', '')}\n"
        f"Пароль: {data.get('password', '')}\n"
        f"Почта: {data.get('email', 'не указана')}\n"
        f"Медиа: {len(data.get('media_files', []))} файлов\n\n"
        f"Всё верно? (да/нет)"
    )
    msg = bot.send_message(message.chat.id, confirm_text)
    bot.register_next_step_handler(msg, save_account, user_id, original_msg_id)

def save_account(message, user_id, original_msg_id):
    if message.text.lower() != "да":
        data = add_data.get(user_id, {})
        for f in data.get('media_files', []):
            if os.path.exists(f):
                os.remove(f)
        if user_id in add_data:
            del add_data[user_id]
        bot.send_message(message.chat.id, "❌ Отменено.", reply_markup=get_menu_keyboard(user_id))
        return
    data = add_data.get(user_id, {})
    media_files = data.get('media_files', [])
    media_paths = []
    for temp_path in media_files:
        if os.path.exists(temp_path):
            extension = temp_path.split('.')[-1]
            final_path = IMAGES_DIR / f"acc_{datetime.now().timestamp()}_{len(media_paths)}.{extension}"
            shutil.move(temp_path, final_path)
            media_paths.append(str(final_path))
    media_str = "|||".join(media_paths) if media_paths else None
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO accounts (name, trophies, brawlers, price_uah, login, password, email, media)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (data['name'], data['trophies'], data['brawlers'],
          data['price'], data['login'], data['password'], data['email'], media_str))
    conn.commit()
    conn.close()
    if user_id in add_data:
        del add_data[user_id]
    bot.send_message(message.chat.id, "✅ Аккаунт добавлен в базу!", reply_markup=get_menu_keyboard(user_id))
    bot.send_message(message.chat.id, "👑 Админ-панель", reply_markup=admin_panel_keyboard())

def admin_list(call):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name, price_uah, sold, reserved, seller_id FROM accounts")
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.edit_message_text(
            "База пуста.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
        return
    text = "📋 Список аккаунтов:\n\n"
    for acc_id, name, price_uah, sold, reserved, seller_id in accounts:
        status = "🔴 ПРОДАН" if sold else "🟡 ЗАБРОНИРОВАН" if reserved else "🟢 В НАЛИЧИИ"
        seller_info = f" (продавец: {seller_id})" if seller_id else " (админский)"
        price_stars = int(price_uah * UAH_TO_STARS)
        text += f"{acc_id}. {name} — {price_uah} ₴ / {price_stars} ⭐ {status}{seller_info}\n"
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def admin_delete_start(call):
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT id, name FROM accounts WHERE sold = 0")
    accounts = cur.fetchall()
    conn.close()
    if not accounts:
        bot.edit_message_text(
            "Нет доступных аккаунтов для удаления.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id
        )
        bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
        bot.answer_callback_query(call.id)
        return
    keyboard = InlineKeyboardMarkup(row_width=1)
    for acc_id, name in accounts:
        keyboard.add(InlineKeyboardButton(f"❌ {name} (ID: {acc_id})", callback_data=f"del_{acc_id}"))
    bot.edit_message_text(
        "Выберите аккаунт для удаления:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=keyboard
    )
    bot.send_message(call.message.chat.id, "🔙 Отмена", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id)

def admin_delete_confirm(call):
    acc_id = int(call.data.split("_")[1])
    conn = sqlite3.connect("accounts.db")
    cur = conn.cursor()
    cur.execute("SELECT media FROM accounts WHERE id = ?", (acc_id,))
    result = cur.fetchone()
    if result and result[0]:
        for path in result[0].split("|||"):
            if os.path.exists(path):
                os.remove(path)
    cur.execute("DELETE FROM accounts WHERE id = ?", (acc_id,))
    conn.commit()
    conn.close()
    bot.edit_message_text(
        f"✅ Аккаунт ID {acc_id} удалён.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id
    )
    bot.send_message(call.message.chat.id, "🔙 Назад", reply_markup=back_keyboard())
    bot.answer_callback_query(call.id, "✅ Аккаунт удалён")

if __name__ == "__main__":
    print("🤖 Бот запущен...")
    print(f"✅ Админы: {ADMIN_IDS}")
    print(f"✅ Канал для отзывов: {CHANNEL_ID}")
    print(f"✅ Курс: 1 ₴ = {UAH_TO_STARS} ⭐")
    print(f"✅ Комиссия бота: {COMMISSION_PERCENT}%")
    print("✅ Банк: OTP Bank")
    print("✅ Оплата звёздами через подарок")
    while True:
        try:
            bot.polling(none_stop=True, interval=2, timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            print("🔄 Переподключение через 5 секунд...")
            time.sleep(5) 
