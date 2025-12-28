import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Bot token, username va kanalni o'zgartiring
BOT_TOKEN = '7097834567:AAE7cBURXPJ83j9mEN9ncoyw3oJVlvQDmMo'
BOT_USERNAME = '@RailwaysChannel_bot'  # Masalan: myreferalbot
CHANNEL_USERNAME = '@aba20012003'  # Masalan: @my_channel
CHANNEL_URL = f'https://t.me/{CHANNEL_USERNAME.lstrip("@")}'

# Logging
logging.basicConfig(level=logging.INFO)

# FSM states
class UserStates(StatesGroup):
    choosing_language = State()
    checking_subscription = State()

# Database init
def init_db():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            language TEXT,
            balance INTEGER DEFAULT 0,
            referred_by INTEGER,
            subscribed BOOLEAN DEFAULT FALSE
        )
    ''')
    conn.commit()
    conn.close()

# User qo'shish/yangilash
def add_or_update_user(user_id: int, language: str = None, referred_by: int = None):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if not user:
        cursor.execute('INSERT INTO users (user_id, language, referred_by) VALUES (?, ?, ?)',
                       (user_id, language, referred_by))
    else:
        if language:
            cursor.execute('UPDATE users SET language = ? WHERE user_id = ?', (language, user_id))
    if referred_by:
        cursor.execute('UPDATE users SET balance = balance + 1 WHERE user_id = ?', (referred_by,))
    conn.commit()
    conn.close()

# Obuna holatini yangilash
def update_subscription(user_id: int, subscribed: bool):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET subscribed = ? WHERE user_id = ?', (subscribed, user_id))
    conn.commit()
    conn.close()

# Obuna tekshirish
async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# Til olish
def get_user_language(user_id: int) -> str:
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT language FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# Obuna holati
def get_user_subscribed(user_id: int) -> bool:
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT subscribed FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else False

# Balans
def get_user_balance(user_id: int) -> int:
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

# Matnlar
def get_text(key: str, lang: str) -> str:
    texts = {
        'uz': {
            'welcome': "🇺🇿 Xush kelibsiz! Tilni tanlang:",
            'subscribe_prompt': "🔥 Botdan foydalanish uchun quyidagi kanalga obuna bo'ling:",
            'channel_button': "📢 Kanalga o'tish",
            'check_button': "✅ Tekshirish",
            'not_subscribed': "❌ Siz hali obuna bo'lmagansiz!\nObuna bo'lib, qayta tekshiring.",
            'subscribed': "🎉 Tabriklaymiz! Siz muvaffaqiyatli obuna bo'ldingiz.\n\nSizning shaxsiy referral linkingiz:\n",
            'balance': "👤 Ballarim",
            'admin': "📞 Admin",
        },
        'ru': {
            'welcome': "🇷🇺 Добро пожаловать! Выберите язык:",
            'subscribe_prompt': "🔥 Чтобы использовать бота, подпишитесь на канал:",
            'channel_button': "📢 Перейти в канал",
            'check_button': "✅ Проверить",
            'not_subscribed': "❌ Вы еще не подписаны!\nПодпишитесь и проверьте снова.",
            'subscribed': "🎉 Поздравляем! Вы успешно подписались.\n\nВаша личная реферальная ссылка:\n",
            'balance': "👤 Мои баллы",
            'admin': "📞 Админ",
        }
    }
    return texts.get(lang, texts['uz']).get(key, '')

# Til tanlash keyboard
def get_language_keyboard() -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
    ])
    return keyboard

# Yangi chiroyli subscription keyboard: kanal tugmasi + tekshirish tugmasi
def get_subscribe_keyboard(lang: str) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('channel_button', lang), url=CHANNEL_URL)],
        [InlineKeyboardButton(text=get_text('check_button', lang), callback_data="check_sub")],
    ])
    return keyboard

# Menu reply keyboard
def get_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    keyboard = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=get_text('balance', lang))],
        [KeyboardButton(text=get_text('admin', lang))],
    ], resize_keyboard=True)
    return keyboard

# Main
async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    @dp.message(Command('start'))
    async def start_handler(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        args = message.text.split()[1:] if len(message.text.split()) > 1 else None
        referred_by = int(args[0]) if args and args[0].isdigit() else None
        add_or_update_user(user_id, referred_by=referred_by)

        lang = get_user_language(user_id)
        if not lang:
            await message.answer(get_text('welcome', 'uz'), reply_markup=get_language_keyboard())
            await state.set_state(UserStates.choosing_language)
            return

        if get_user_subscribed(user_id):
            referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
            await message.answer(
                f"{get_text('subscribed', lang)}<code>{referral_link}</code>",
                parse_mode="HTML",
                reply_markup=get_menu_keyboard(lang)
            )
        else:
            await message.answer(
                get_text('subscribe_prompt', lang),
                reply_markup=get_subscribe_keyboard(lang)
            )
            await state.set_state(UserStates.checking_subscription)

    @dp.callback_query(lambda c: c.data.startswith('lang_'))
    async def language_callback(callback: types.CallbackQuery, state: FSMContext):
        lang = callback.data.split('_')[1]
        user_id = callback.from_user.id
        add_or_update_user(user_id, language=lang)

        await callback.message.edit_text(
            get_text('subscribe_prompt', lang),
            reply_markup=get_subscribe_keyboard(lang)
        )
        await state.set_state(UserStates.checking_subscription)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == 'check_sub')
    async def check_sub_callback(callback: types.CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = get_user_language(user_id)

        subscribed = await is_subscribed(callback.bot, user_id)
        if subscribed:
            update_subscription(user_id, True)
            referral_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
            await callback.message.edit_text(
                f"{get_text('subscribed', lang)}<code>{referral_link}</code>",
                parse_mode="HTML"
            )
            await callback.message.answer("🏠 Asosiy menu:", reply_markup=get_menu_keyboard(lang))
            await state.clear()
        else:
            await callback.answer(get_text('not_subscribed', lang), show_alert=True)

    @dp.message()
    async def menu_handler(message: types.Message):
        user_id = message.from_user.id
        lang = get_user_language(user_id)
        text = message.text

        if get_text('balance', lang) in text:
            balance = get_user_balance(user_id)
            await message.answer(f"👤 {get_text('balance', lang)}: <b>{balance}</b>", parse_mode="HTML")
        elif get_text('admin', lang) in text:
            await message.answer("📞 Admin: +998947301030")

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())