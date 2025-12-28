import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncpg

# Environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME')
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME')
DATABASE_URL = os.getenv('DATABASE_URL')
CHANNEL_URL = f'https://t.me/{CHANNEL_USERNAME.lstrip("@")}'

logging.basicConfig(level=logging.INFO)

class UserStates(StatesGroup):
    choosing_language = State()
    checking_subscription = State()

pool = None

async def create_pool():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

async def init_db():
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                language TEXT,
                balance INTEGER DEFAULT 0,
                referred_by BIGINT,
                subscribed BOOLEAN DEFAULT FALSE
            )
        ''')

async def add_or_update_user(user_id: int, language: str = None, referred_by: int = None):
    async with pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO users (user_id, language, referred_by)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET language = EXCLUDED.language
        ''', user_id, language, referred_by)
        if referred_by:
            await conn.execute('UPDATE users SET balance = balance + 1 WHERE user_id = $1', referred_by)

async def update_subscription(user_id: int, subscribed: bool):
    async with pool.acquire() as conn:
        await conn.execute('UPDATE users SET subscribed = $1 WHERE user_id = $2', subscribed, user_id)

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logging.error(f"Obuna tekshirishda xato: {e}")
        return False

async def get_user_language(user_id: int) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT language FROM users WHERE user_id = $1', user_id)
        return row['language'] if row else None

async def get_user_subscribed(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT subscribed FROM users WHERE user_id = $1', user_id)
        return row['subscribed'] if row else False

async def get_user_balance(user_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT balance FROM users WHERE user_id = $1', user_id)
        return row['balance'] if row else 0

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

def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="lang_uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru")],
    ])

def get_subscribe_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_text('channel_button', lang), url=CHANNEL_URL)],
        [InlineKeyboardButton(text=get_text('check_button', lang), callback_data="check_sub")],
    ])

def get_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=get_text('balance', lang))],
        [KeyboardButton(text=get_text('admin', lang))],
    ], resize_keyboard=True)

async def main():
    await create_pool()
    await init_db()
    bot = Bot(token=BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    @dp.message(Command('start'))
    async def start_handler(message: types.Message, state: FSMContext):
        user_id = message.from_user.id
        args = message.text.split()[1:] if len(message.text.split()) > 1 else None
        referred_by = int(args[0]) if args and args[0].isdigit() else None
        await add_or_update_user(user_id, referred_by=referred_by)
        lang = await get_user_language(user_id)
        if not lang:
            await message.answer(get_text('welcome', 'uz'), reply_markup=get_language_keyboard())
            await state.set_state(UserStates.choosing_language)
            return
        if await get_user_subscribed(user_id):
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
        await add_or_update_user(user_id, language=lang)
        await callback.message.edit_text(
            get_text('subscribe_prompt', lang),
            reply_markup=get_subscribe_keyboard(lang)
        )
        await state.set_state(UserStates.checking_subscription)
        await callback.answer()

    @dp.callback_query(lambda c: c.data == 'check_sub')
    async def check_sub_callback(callback: types.CallbackQuery, state: FSMContext):
        user_id = callback.from_user.id
        lang = await get_user_language(user_id)
        subscribed = await is_subscribed(callback.bot, user_id)
        if subscribed:
            await update_subscription(user_id, True)
            referral_link = f"t.me/{BOT_USERNAME}?start={user_id}"
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
        lang = await get_user_language(user_id)
        text = message.text

        if get_text('balance', lang) in text:
            balance = await get_user_balance(user_id)
            await message.answer(f"👤 {get_text('balance', lang)}: <b>{balance}</b>", parse_mode="HTML")
        elif get_text('admin', lang) in text:
            admin_phone = os.getenv('ADMIN_PHONE', '+998947301030')
            admin_username = os.getenv('ADMIN_USERNAME', '@admin')
            await message.answer(
                f"📞 Admin bilan bog‘lanish:\n"
                f"Raqam: {admin_phone}\n"
                f"Telegram: {admin_username}"
            )

    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())


