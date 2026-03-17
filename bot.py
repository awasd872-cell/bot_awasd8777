import asyncio
import random
import string
import sqlite3
import json
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import logging

# ========== НАСТРОЙКИ ДЛЯ RENDER ==========
# Берем токен из переменных окружения (БЕЗОПАСНОСТЬ!)
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8564052664:AAER6YsL8SoDZ5qbP6t_2dYdllvGNgvoRkI")
ADMIN_IDS = [2044932905]
SECRET_ADMIN_COMMAND = "goneadmintopsecret"

MIN_USERNAME_LENGTH = 5
MAX_USERNAME_LENGTH = 6
SUBSCRIPTION_DAYS = 30

# Настройка логирования для Render
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_name="bot_database.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_name)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    subscription_key TEXT,
                    is_active BOOLEAN DEFAULT 0,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица ключей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscription_keys (
                    key TEXT PRIMARY KEY,
                    is_used BOOLEAN DEFAULT 0,
                    used_by_user_id INTEGER,
                    used_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER
                )
            ''')

            # Таблица сессий поиска
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS search_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    length INTEGER,
                    use_digits BOOLEAN,
                    checked_count INTEGER DEFAULT 0,
                    found_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    waiting_for_response BOOLEAN DEFAULT 0,
                    current_username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица найденных юзернеймов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS found_usernames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    session_id INTEGER,
                    found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица логов админа
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT,
                    details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()
            logger.info("✅ База данных готова")

    # ===== ВСЕ МЕТОДЫ БАЗЫ ДАННЫХ (ОСТАЛИСЬ БЕЗ ИЗМЕНЕНИЙ) =====
    def add_user(self, user_id, username=None, first_name=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, username, first_name)
                VALUES (?, ?, ?)
            ''', (user_id, username, first_name))
            conn.commit()

    def check_subscription(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT is_active, expires_at FROM users 
                WHERE user_id = ?
            ''', (user_id,))
            result = cursor.fetchone()

            if not result or not result[0]:
                return False

            expires_at = datetime.fromisoformat(result[1]) if result[1] else None
            return expires_at and expires_at > datetime.now()

    def activate_subscription(self, user_id, key):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            expires_at = datetime.now() + timedelta(days=SUBSCRIPTION_DAYS)

            cursor.execute('''
                UPDATE users 
                SET subscription_key = ?, is_active = 1, expires_at = ?
                WHERE user_id = ?
            ''', (key, expires_at.isoformat(), user_id))

            cursor.execute('''
                UPDATE subscription_keys 
                SET is_used = 1, used_by_user_id = ?, used_at = ?
                WHERE key = ?
            ''', (user_id, datetime.now().isoformat(), key))

            conn.commit()

    def generate_keys(self, count=10, created_by=None):
        keys = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for _ in range(count):
                key = 'TG' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=14))
                cursor.execute('''
                    INSERT INTO subscription_keys (key, created_by)
                    VALUES (?, ?)
                ''', (key, created_by))
                keys.append(key)
            conn.commit()
        return keys

    def check_key(self, key):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM subscription_keys 
                WHERE key = ? AND is_used = 0
            ''', (key,))
            return cursor.fetchone() is not None

    def create_session(self, user_id, length, use_digits):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO search_sessions 
                (user_id, length, use_digits, checked_count, found_count, status, waiting_for_response)
                VALUES (?, ?, ?, 0, 0, 'active', 0)
            ''', (user_id, length, 1 if use_digits else 0))
            conn.commit()
            return cursor.lastrowid

    def set_waiting(self, session_id, username):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE search_sessions 
                SET waiting_for_response = 1, current_username = ?
                WHERE id = ?
            ''', (username, session_id))
            conn.commit()

    def clear_waiting(self, session_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE search_sessions 
                SET waiting_for_response = 0, current_username = NULL
                WHERE id = ?
            ''', (session_id,))
            conn.commit()

    def is_waiting(self, session_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT waiting_for_response FROM search_sessions WHERE id = ?
            ''', (session_id,))
            result = cursor.fetchone()
            return result[0] == 1 if result else False

    def stop_session(self, session_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE search_sessions SET status = 'stopped', waiting_for_response = 0 WHERE id = ?
            ''', (session_id,))
            conn.commit()

    def get_session_status(self, session_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT status FROM search_sessions WHERE id = ?
            ''', (session_id,))
            result = cursor.fetchone()
            return result[0] if result else 'stopped'

    def save_found_username(self, username, session_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO found_usernames (username, session_id)
                    VALUES (?, ?)
                ''', (username, session_id))
                conn.commit()
            except:
                pass

    def update_session_stats(self, session_id, checked, found):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE search_sessions 
                SET checked_count = ?, found_count = ? 
                WHERE id = ?
            ''', (checked, found, session_id))
            conn.commit()

    def get_users_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM users")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
            active = cursor.fetchone()[0]
            return {"total": total, "active": active}

    def get_keys_stats(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM subscription_keys")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM subscription_keys WHERE is_used = 1")
            used = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM subscription_keys WHERE is_used = 0")
            free = cursor.fetchone()[0]
            return {"total": total, "used": used, "free": free}


# СОЗДАЕМ БАЗУ
db = Database()


# ========== ПРОВЕРКА ЮЗЕРНЕЙМОВ ==========
async def check_username(username: str) -> bool:
    url = f"https://t.me/{username}"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, allow_redirects=False, timeout=10) as response:
                status = response.status

                if status in [301, 302, 307, 308]:
                    location = response.headers.get('Location', '')
                    if any(x in location for x in ['search', 'notfound', 'not_exist']):
                        logger.info(f"✅ {username} - СВОБОДЕН")
                        return True
                    else:
                        return False

                elif status == 200:
                    html = await response.text()
                    if 'tgme_page_photo' in html or 'tgme_page_title' in html:
                        return False
                    else:
                        logger.info(f"✅ {username} - СВОБОДЕН")
                        return True

                else:
                    return True

        except Exception as e:
            logger.info(f"⚠️ {username} - ОШИБКА: {e}")
            return False


# ========== ГЕНЕРАТОР ==========
def generate_usernames(length: int, use_digits: bool):
    chars = string.ascii_lowercase
    if use_digits:
        chars += string.digits

    seen = set()
    while True:
        username = ''.join(random.choices(chars, k=length))
        if username not in seen:
            seen.add(username)
            yield username


# ========== БОТ ==========
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


class States(StatesGroup):
    waiting_for_key = State()
    waiting_for_length = State()
    waiting_for_digits = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ========== КОМАНДЫ ==========
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    db.add_user(user_id, message.from_user.username, message.from_user.first_name)

    if db.check_subscription(user_id):
        await message.answer(f"👋 Введите длину юзернейма (от {MIN_USERNAME_LENGTH} до {MAX_USERNAME_LENGTH}):")
        await state.set_state(States.waiting_for_length)
    else:
        await message.answer("🔐 Введите ключ подписки:")
        await state.set_state(States.waiting_for_key)


@dp.message(Command(SECRET_ADMIN_COMMAND))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Доступ запрещен")

    users = db.get_users_stats()
    keys = db.get_keys_stats()

    text = (
        f"👑 **Админ-панель**\n\n"
        f"👥 Пользователей: {users['total']}\n"
        f"✅ Активных: {users['active']}\n"
        f"🔑 Ключей всего: {keys['total']}\n"
        f"💚 Свободно: {keys['free']}\n"
        f"📌 Использовано: {keys['used']}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Создать 10 ключей", callback_data="gen_keys")]
    ])

    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query(lambda c: c.data == "gen_keys")
async def gen_keys(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Доступ запрещен", show_alert=True)

    keys = db.generate_keys(10, callback.from_user.id)
    keys_text = "\n".join(keys)
    await callback.message.edit_text(
        f"✅ **Сгенерировано 10 ключей:**\n\n`{keys_text}`",
        parse_mode="Markdown"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Назад", callback_data="back_to_admin")]
    ])
    await callback.message.edit_reply_markup(reply_markup=keyboard)


@dp.callback_query(lambda c: c.data == "back_to_admin")
async def back_to_admin(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔")

    users = db.get_users_stats()
    keys = db.get_keys_stats()

    text = f"👑 Админ-панель\n\n👥 {users['total']} | ✅ {users['active']} | 🔑 {keys['total']} | 💚 {keys['free']}"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔑 Создать 10 ключей", callback_data="gen_keys")]
    ])

    await callback.message.edit_text(text, reply_markup=keyboard)


@dp.message(States.waiting_for_key)
async def process_key(message: Message, state: FSMContext):
    key = message.text.strip().upper()

    if db.check_key(key):
        db.activate_subscription(message.from_user.id, key)
        await message.answer(
            f"✅ **Ключ активирован!**\n\n"
            f"Теперь введите длину юзернейма (от {MIN_USERNAME_LENGTH} до {MAX_USERNAME_LENGTH}):",
            parse_mode="Markdown"
        )
        await state.set_state(States.waiting_for_length)
    else:
        await message.answer("❌ **Неверный ключ!** Попробуйте еще:", parse_mode="Markdown")


@dp.message(States.waiting_for_length)
async def process_length(message: Message, state: FSMContext):
    try:
        length = int(message.text.strip())

        if length < MIN_USERNAME_LENGTH or length > MAX_USERNAME_LENGTH:
            await message.answer(f"❌ Длина должна быть от {MIN_USERNAME_LENGTH} до {MAX_USERNAME_LENGTH}")
            return

        await state.update_data(length=length)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data="digits_yes"),
                InlineKeyboardButton(text="❌ Нет", callback_data="digits_no")
            ]
        ])

        await message.answer("🔢 **Разрешать цифры?**", reply_markup=keyboard, parse_mode="Markdown")
        await state.set_state(States.waiting_for_digits)

    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")


@dp.callback_query(States.waiting_for_digits)
async def process_digits(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    use_digits = (callback.data == "digits_yes")

    # Создаем сессию
    session_id = db.create_session(callback.from_user.id, data['length'], use_digits)

    await callback.message.edit_text(
        f"🔍 **НАЧИНАЮ ПОИСК**\n\n"
        f"📏 Длина: {data['length']}\n"
        f"🔢 Цифры: {'✅' if use_digits else '❌'}\n\n"
        f"⏳ Ищу свободные юзернеймы...\n"
        f"_Буду ждать нажатия ПРОДОЛЖИТЬ после каждой находки_"
    )

    await state.clear()
    # Запускаем поиск
    await search_loop(callback.message, session_id, data['length'], use_digits, callback.from_user.id)


# ========== ОСНОВНОЙ ЦИКЛ ПОИСКА ==========
async def search_loop(message: Message, session_id: int, length: int, use_digits: bool, user_id: int):
    """Поиск с ожиданием решения пользователя"""

    status_msg = await message.answer("🔄 **Подготовка...**", parse_mode="Markdown")
    start_time = datetime.now()
    checked = 0
    found = 0

    for username in generate_usernames(length, use_digits):
        # Проверяем не остановлена ли сессия
        if db.get_session_status(session_id) == 'stopped':
            await status_msg.edit_text("⏹ **Поиск остановлен**")
            break

        # Проверяем не ждем ли мы ответ на предыдущий
        if db.is_waiting(session_id):
            await asyncio.sleep(1)
            continue

        checked += 1
        is_free = await check_username(username)

        # Обновляем статус
        if checked % 5 == 0:
            elapsed = (datetime.now() - start_time).seconds
            speed = checked / elapsed if elapsed > 0 else 0

            try:
                await status_msg.edit_text(
                    f"🔍 **ПОИСК**\n\n"
                    f"📊 Проверено: {checked}\n"
                    f"🎯 Найдено: {found}\n"
                    f"⚡️ Скорость: {speed:.1f}/сек\n"
                    f"⏱ Время: {elapsed} сек\n"
                    f"🔄 Последний: @{username}"
                )
            except:
                pass

        # Если нашли свободный
        if is_free:
            found += 1

            # Сохраняем в базу
            db.save_found_username(username, session_id)
            db.update_session_stats(session_id, checked, found)
            db.set_waiting(session_id, username)  # Ставим флаг ожидания

            elapsed = (datetime.now() - start_time).seconds

            # Кнопка только ПРОДОЛЖИТЬ
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="▶ ПРОДОЛЖИТЬ", callback_data=f"continue_{session_id}")
                ],
                [
                    InlineKeyboardButton(text="⏹ ОСТАНОВИТЬ ПОИСК", callback_data=f"stop_{session_id}")
                ]
            ])

            # Отправляем находку
            await message.answer(
                f"✅ **НАЙДЕН СВОБОДНЫЙ!**\n\n"
                f"👉 @{username}\n"
                f"👉 [t.me/{username}](https://t.me/{username})\n\n"
                f"📊 **Статистика:**\n"
                f"• Найдено всего: {found}\n"
                f"• Проверено всего: {checked}\n"
                f"• Время поиска: {elapsed} сек\n\n"
                f"⚡️ **Нажмите ПРОДОЛЖИТЬ чтобы искать дальше**",
                reply_markup=keyboard,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

            # Ждем пока пользователь нажмет кнопку (но не бесконечно)
            wait_start = datetime.now()
            while db.is_waiting(session_id):
                # Если прошло больше 2 минут - снимаем флаг ожидания
                if (datetime.now() - wait_start).seconds > 120:
                    db.clear_waiting(session_id)
                    await message.answer("⏰ **Время ожидания вышло. Продолжаю поиск...**")
                    break

                await asyncio.sleep(1)

        # Небольшая задержка для предотвращения бана
        await asyncio.sleep(0.8)


# ========== ОБРАБОТКА КНОПОК ==========
@dp.callback_query(lambda c: c.data.startswith(('continue_', 'stop_')))
async def handle_buttons(callback: CallbackQuery):
    action, session_id = callback.data.split('_')
    session_id = int(session_id)

    if action == 'continue':
        # Просто снимаем флаг ожидания
        db.clear_waiting(session_id)
        await callback.message.edit_text(
            f"▶ **Продолжаю поиск...**\n\n"
            f"Новые находки будут появляться здесь",
            parse_mode="Markdown"
        )

    elif action == 'stop':
        db.stop_session(session_id)
        db.clear_waiting(session_id)

        await callback.message.edit_text(
            f"⏹ **Поиск остановлен**\n\n"
            f"Для нового поиска отправьте /start",
            parse_mode="Markdown"
        )

    await callback.answer()


# ========== ФУНКЦИЯ ДЛЯ RENDER ==========
async def on_startup():
    """Действия при запуске бота"""
    logger.info("🚀 Бот запускается на Render...")
    logger.info(f"🔐 Секретная команда: /{SECRET_ADMIN_COMMAND}")
    logger.info("✅ База данных подключена")
    
    # Отправляем уведомление админу о запуске
    try:
        for admin_id in ADMIN_IDS:
            await bot.send_message(
                admin_id,
                f"🚀 **Бот успешно запущен на Render.com!**\n\n"
                f"📊 **Статус:**\n"
                f"• База данных: ✅ готова\n"
                f"• Режим: polling\n"
                f"• Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                parse_mode="Markdown"
            )
    except:
        pass


async def on_shutdown():
    """Действия при остановке бота"""
    logger.info("🛑 Бот останавливается...")
    await bot.session.close()


# ========== ЗАПУСК ==========
async def main():
    # Регистрируем функции запуска/остановки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    logger.info("🚀 Запуск бота...")
    
    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")