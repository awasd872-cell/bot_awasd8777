import asyncio
import os
import tempfile
import shutil
import secrets
import aiosqlite
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, FSInputFile
from aiogram.enums import ParseMode
from aiohttp import web

# ================= НАСТРОЙКИ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0)) # Сюда передадим твой ID через Render

if not BOT_TOKEN or not ADMIN_ID:
    print("ВНИМАНИЕ: Не указан BOT_TOKEN или ADMIN_ID!")

XOR_KEY = "gonebestincrmp777"
COMPILER_CMD = "i686-w64-mingw32-g++"
DB_NAME = "bot_database.db"

# ================= БАЗА ДАННЫХ =================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT)''')
        await db.execute('''CREATE TABLE IF NOT EXISTS keys (key_text TEXT PRIMARY KEY, is_used INTEGER DEFAULT 0, used_by INTEGER)''')
        await db.commit()

async def check_access(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)) as cursor:
            return await cursor.fetchone() is not None

# ================= C++ ШАБЛОН =================
EMBEDDED_ASI_CODE = r'''// loader_fast_restore.cpp
// ===========================
// ASI Plugin (DLL) - Быстрое восстановление index.html
// Логика: Двойные маркеры (HTML + JS) для надежного удаления
// ===========================

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <string>
#include <vector>
#include <fstream>
#include <sstream>
#include <filesystem>
#include <thread>
#include <chrono>
#include <random>

#pragma comment(lib, "ws2_32.lib")

namespace fs = std::filesystem;

// ---------------------- Настройки ----------------------
static const char* INDEX_PATH    = "uiresources\\index.html";
static const char* INDEX_BACKUP  = "uiresources\\index_backup.html";
static const char* INJECT_MARKER = "<!-- HUD_JS_INJECTED -->"; // HTML маркер в начале
static const char* JS_END_MARKER = "// HUD_INJECTION_END_XYZ123"; // JS маркер в конце

// =======================================================
// !!! СЮДА ВСТАВИТЬ ЗАШИФРОВАННЫЙ МАССИВ ИЗ PYTHON СКРИПТА !!!
// =======================================================
static const unsigned char EMBEDDED_JS_DATA[] = {
    /* EMBED_JS_DATA_HERE */
};
// =======================================================

// ----------------- Вспомогательные функции -----------------

// ФУНКЦИЯ XOR-ДЕШИФРОВАНИЯ ИЗ ВТОРОГО ИСХОДНИКА
static std::string decrypt_js_data(const unsigned char* data, size_t size) {
    if (size <= 1) return "";
    
    std::string result;
    result.reserve(size);
    
    // ФИКСИРОВАННЫЙ ключ - ДОЛЖЕН СОВПАДАТЬ С КЛЮЧОМ В PYTHON!
    std::string key = "gonebestincrmp777"; // ← ПОМЕНЯЙ НА СВОЙ КЛЮЧ!
    
    size_t keyIndex = 0;
    
    for (size_t i = 0; i < size; i++) {
        char decrypted = data[i] ^ key[keyIndex];
        result.push_back(decrypted);
        keyIndex = (keyIndex + 1) % key.length();
    }
    
    return result;
}

static std::string get_game_root() {
    char buf[MAX_PATH];
    GetModuleFileNameA(NULL, buf, MAX_PATH);
    std::string s(buf);
    size_t pos = s.find_last_of("\\/");
    return (pos == std::string::npos) ? s : s.substr(0, pos);
}

static std::string combine_paths(const std::string& path1, const std::string& path2) {
    if (path1.empty()) return path2;
    if (path2.empty()) return path1;
    char last_char = path1[path1.size() - 1];
    if (last_char == '\\' || last_char == '/') return path1 + path2;
    return path1 + "\\" + path2;
}

// ------------- Сборка фрагмента с двойными маркерами -------------
static std::string build_fragment_with_hud_js(const std::string& hudJs) {
    std::string s;
    s.reserve(hudJs.size() + 300);

    // HTML маркер в начале
    s.append("\n");
    s.append(INJECT_MARKER);
    s.append("\n");

    // Начало скрипта
    s.append("<script>(function(){\n");
    s.append("  try {(function(){\n");
    
    // Вставляем пользовательский JS код
    s.append(hudJs);
    
    // JS маркер в конце перед закрывающими скобками
    s.append("\n    ");
    s.append(JS_END_MARKER);
    s.append("\n");
    
    // Закрываем функции и добавляем fetch
    s.append("  })();}catch(e){console.error('HUD inject error', e);}\n");
    s.append("  try {fetch('http://127.0.0.1:19191/hud-ready').catch(function(){});}catch(e){}\n");
    
    // Конец скрипта
    s.append("})();</script>\n");

    return s;
}

// Быстрое создание/обновление бэкапа
static bool create_or_update_backup(const std::string& srcPath, const std::string& dstPath) {
    try {
        if (!fs::exists(srcPath)) return false;
        
        // Проверяем, отличается ли текущий файл от бэкапа
        if (fs::exists(dstPath)) {
            auto src_time = fs::last_write_time(srcPath);
            auto dst_time = fs::last_write_time(dstPath);
            if (src_time <= dst_time) {
                // Проверяем содержимое
                std::ifstream src(srcPath, std::ios::binary);
                std::ifstream dst(dstPath, std::ios::binary);
                if (src && dst) {
                    std::string src_content((std::istreambuf_iterator<char>(src)), 
                                          std::istreambuf_iterator<char>());
                    std::string dst_content((std::istreambuf_iterator<char>(dst)), 
                                          std::istreambuf_iterator<char>());
                    if (src_content == dst_content) {
                        return true; // Бэкап актуален
                    }
                }
            }
        }
        
        // Создаем/обновляем бэкап
        fs::copy(srcPath, dstPath, fs::copy_options::overwrite_existing);
        return true;
    } catch (...) {
        return false;
    }
}

// СУПЕР БЫСТРОЕ ВОССТАНОВЛЕНИЕ из бэкапа
static bool fast_restore_from_backup(const std::string& srcPath, const std::string& dstPath) {
    try {
        if (!fs::exists(srcPath)) return false;
        
        // Просто копируем бэкап обратно
        fs::copy(srcPath, dstPath, fs::copy_options::overwrite_existing);
        return true;
    } catch (...) {
        // Если не получилось напрямую, пробуем через временный файл
        try {
            std::string tempPath = dstPath + ".tmp";
            fs::copy(srcPath, tempPath, fs::copy_options::overwrite_existing);
            fs::rename(tempPath, dstPath);
            return true;
        } catch (...) {
            return false;
        }
    }
}

// Умное удаление только инжектированного скрипта
static bool remove_injected_script_smart(const std::string& indexPath) {
    try {
        if (!fs::exists(indexPath)) return false;
        
        std::ifstream in(indexPath, std::ios::binary);
        if (!in.is_open()) return false;
        
        std::string content((std::istreambuf_iterator<char>(in)), 
                           std::istreambuf_iterator<char>());
        in.close();
        
        bool changed = false;
        
        // СПОСОБ 1: Ищем по HTML маркеру
        size_t start_pos = content.find(INJECT_MARKER);
        if (start_pos != std::string::npos) {
            // Ищем закрывающий </script> после маркера
            size_t end_pos = content.find("</script>", start_pos);
            if (end_pos != std::string::npos) {
                end_pos += 9; // + длина "</script>"
                content.erase(start_pos, end_pos - start_pos);
                changed = true;
            }
        }
        
        // СПОСОБ 2: Если HTML маркер не найден, ищем по JS маркеру
        if (!changed) {
            size_t js_marker_pos = content.find(JS_END_MARKER);
            if (js_marker_pos != std::string::npos) {
                // Ищем начало <script перед маркером
                size_t script_start = content.rfind("<script", js_marker_pos);
                if (script_start != std::string::npos) {
                    // Ищем закрывающий </script> после маркера
                    size_t script_end = content.find("</script>", js_marker_pos);
                    if (script_end != std::string::npos) {
                        script_end += 9;
                        content.erase(script_start, script_end - script_start);
                        changed = true;
                    }
                }
            }
        }
        
        // СПОСОБ 3: Ищем по сигнатуре fetch (последняя попытка)
        if (!changed) {
            size_t fetch_pos = content.find("fetch('http://127.0.0.1:19191/hud-ready')");
            if (fetch_pos != std::string::npos) {
                size_t script_start = content.rfind("<script", fetch_pos);
                if (script_start != std::string::npos) {
                    size_t script_end = content.find("</script>", fetch_pos);
                    if (script_end != std::string::npos) {
                        script_end += 9;
                        content.erase(script_start, script_end - script_start);
                        changed = true;
                    }
                }
            }
        }
        
        if (changed) {
            std::ofstream out(indexPath, std::ios::binary | std::ios::trunc);
            if (!out.is_open()) return false;
            out << content;
            return true;
        }
        
        return false; // Нечего удалять
        
    } catch (...) {
        return false;
    }
}

// Умное восстановление: сначала удаляем скрипт, потом бэкап
static bool smart_restore(const std::string& indexPath, const std::string& backupPath) {
    // ШАГ 1: Пытаемся быстро удалить только скрипт
    if (remove_injected_script_smart(indexPath)) {
        return true; // Успешно удалили только инжектированную часть
    }
    
    // ШАГ 2: Если не удалось, восстанавливаем из бэкапа
    if (fs::exists(backupPath)) {
        return fast_restore_from_backup(backupPath, indexPath);
    }
    
    // ШАГ 3: Если нет бэкапа, пытаемся найти и удалить вручную
    try {
        if (!fs::exists(indexPath)) return false;
        
        std::ifstream in(indexPath, std::ios::binary);
        if (!in.is_open()) return false;
        
        std::string content((std::istreambuf_iterator<char>(in)), 
                           std::istreambuf_iterator<char>());
        in.close();
        
        // Ищем любой из маркеров
        if (content.find(INJECT_MARKER) != std::string::npos || 
            content.find(JS_END_MARKER) != std::string::npos) {
            // Создаем чистый файл
            std::ofstream out(indexPath, std::ios::binary | std::ios::trunc);
            if (!out.is_open()) return false;
            
            // Записываем что-то минимальное
            out << "<html><body></body></html>";
            return true;
        }
    } catch (...) {}
    
    return false;
}

// Проверка, уже ли вставлен фрагмент (по любому маркеру)
static bool is_already_injected(const std::string& indexPath) {
    try {
        std::ifstream in(indexPath, std::ios::binary);
        if (!in.is_open()) return false;
        std::string content((std::istreambuf_iterator<char>(in)), 
                           std::istreambuf_iterator<char>());
        // Проверяем оба маркера
        return content.find(INJECT_MARKER) != std::string::npos || 
               content.find(JS_END_MARKER) != std::string::npos;
    } catch (...) {
        return false;
    }
}

static bool inject_fragment(const std::string& indexPath, const std::string& fragment) {
    try {
        // Читаем весь файл
        std::ifstream in(indexPath, std::ios::binary);
        if (!in.is_open()) return false;
        std::string content((std::istreambuf_iterator<char>(in)), 
                           std::istreambuf_iterator<char>());
        in.close();

        // Ищем место для вставки (перед </body>)
        size_t pos = content.find("</body>");
        if (pos == std::string::npos) pos = content.find("</BODY>");
        if (pos == std::string::npos) {
            // Если нет body, вставляем перед </html>
            pos = content.find("</html>");
            if (pos == std::string::npos) pos = content.find("</HTML>");
        }
        
        if (pos == std::string::npos) {
            // Если ничего не найдено, добавляем в конец
            content += fragment;
        } else {
            content.insert(pos, fragment);
        }

        // Записываем обратно
        std::ofstream out(indexPath, std::ios::binary | std::ios::trunc);
        if (!out.is_open()) return false;
        out << content;
        return true;
    } catch (...) { 
        return false; 
    }
}

// ---------------- Mini HTTP server ----------------
static void start_local_server_and_wait_for_ready(const std::string& indexPath, 
                                                  const std::string& backupPath) {
    WSADATA wsa;
    SOCKET listen_sock = INVALID_SOCKET, client = INVALID_SOCKET;
    sockaddr_in server_addr;

    if (WSAStartup(MAKEWORD(2,2), &wsa) != 0) return;

    listen_sock = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (listen_sock == INVALID_SOCKET) { WSACleanup(); return; }

    ZeroMemory(&server_addr, sizeof(server_addr));
    server_addr.sin_family = AF_INET;
    server_addr.sin_addr.s_addr = inet_addr("127.0.0.1");
    server_addr.sin_port = htons(19191);

    int opt = 1;
    setsockopt(listen_sock, SOL_SOCKET, SO_REUSEADDR, (const char*)&opt, sizeof(opt));

    if (bind(listen_sock, (sockaddr*)&server_addr, sizeof(server_addr)) == SOCKET_ERROR) {
        closesocket(listen_sock); WSACleanup(); return;
    }
    if (listen(listen_sock, 1) == SOCKET_ERROR) {
        closesocket(listen_sock); WSACleanup(); return;
    }

    const int TIMEOUT_SECONDS = 30; // Уменьшил таймаут для скорости
    auto start = std::chrono::steady_clock::now();
    char buffer[1024];
    bool got_ready = false;

    // Неблокирующий режим для быстрого выхода
    u_long mode = 1;
    ioctlsocket(listen_sock, FIONBIO, &mode);

    while (true) {
        fd_set readfds; 
        FD_ZERO(&readfds); 
        FD_SET(listen_sock, &readfds);
        
        timeval tv = {0, 100000}; // 100ms таймаут для отзывчивости
        
        if (select(0, &readfds, NULL, NULL, &tv) > 0 && FD_ISSET(listen_sock, &readfds)) {
            client = accept(listen_sock, NULL, NULL);
            if (client != INVALID_SOCKET) {
                int len = recv(client, buffer, sizeof(buffer)-1, 0);
                if (len > 0) {
                    buffer[len] = '\0';
                    if (strstr(buffer, "GET /hud-ready") || strstr(buffer, "/hud-ready")) {
                        // Отправляем быстрый ответ
                        const char* response = 
                            "HTTP/1.1 200 OK\r\n"
                            "Connection: close\r\n"
                            "Content-Length: 2\r\n"
                            "\r\n"
                            "OK";
                        send(client, response, (int)strlen(response), 0);
                        got_ready = true;
                    }
                }
                closesocket(client);
                
                if (got_ready) break; // Немедленный выход
            }
        }
        
        // Проверяем таймаут
        auto elapsed = std::chrono::duration_cast<std::chrono::seconds>(
            std::chrono::steady_clock::now() - start).count();
        
        if (elapsed > TIMEOUT_SECONDS) {
            // Таймаут - все равно восстанавливаем
            break;
        }
        
        // Короткая пауза для CPU
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    closesocket(listen_sock);
    WSACleanup();

    // СРАЗУ ВОССТАНАВЛИВАЕМ ФАЙЛ
    if (got_ready || true) { // Всегда восстанавливаем, даже если timeout
        // Даем HUD немного времени на загрузку
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
        
        // УМНОЕ ВОССТАНОВЛЕНИЕ
        smart_restore(indexPath, backupPath);
        
        // Дополнительная проверка через 100ms
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        if (is_already_injected(indexPath)) {
            // Если маркеры остались, пробуем еще раз
            smart_restore(indexPath, backupPath);
        }
    }
}

// ---------------- Main thread ----------------
DWORD WINAPI InitThread(LPVOID) {
    // Ждем немного, чтобы игра загрузилась
    std::this_thread::sleep_for(std::chrono::milliseconds(800));

    std::string root = get_game_root();
    std::string indexPath = combine_paths(root, INDEX_PATH);
    std::string backupPath = combine_paths(root, INDEX_BACKUP);

    // Если уже вставлено — восстанавливаем и выходим
    if (is_already_injected(indexPath)) {
        smart_restore(indexPath, backupPath);
        return 0;
    }

    // Проверка JS кода с использованием XOR дешифрования
    if (sizeof(EMBEDDED_JS_DATA) <= 1) {
        MessageBoxA(NULL, "Нет встроенного JS кода.", "ASI Loader", MB_OK | MB_ICONERROR);
        return 0;
    }

    // ДЕШИФРОВКА JS КОДА С ПОМОЩЬЮ XOR
    std::string hudJs = decrypt_js_data(EMBEDDED_JS_DATA, sizeof(EMBEDDED_JS_DATA));
    if (hudJs.empty()) {
        MessageBoxA(NULL, "Ошибка дешифрования JS кода.", "ASI Loader", MB_OK | MB_ICONERROR);
        return 0;
    }

    // Создаем/обновляем бэкап оригинала
    if (!create_or_update_backup(indexPath, backupPath)) {
        MessageBoxA(NULL, "Не удалось создать бэкап index.html", 
                   "ASI Loader", MB_OK | MB_ICONWARNING);
        // Продолжаем без бэкапа
    }

    // Вставляем фрагмент с двойными маркерами
    std::string fragment = build_fragment_with_hud_js(hudJs);
    
    if (inject_fragment(indexPath, fragment)) {
        // Запускаем сервер и ждем подтверждения от HUD
        start_local_server_and_wait_for_ready(indexPath, backupPath);
    } else {
        // Если не удалось вставить, все равно пытаемся восстановить (на случай предыдущих инжекций)
        smart_restore(indexPath, backupPath);
    }

    return 0;
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD ul_reason_for_call, LPVOID lpReserved) {
    switch (ul_reason_for_call) {
    case DLL_PROCESS_ATTACH:
        DisableThreadLibraryCalls(hModule);
        CreateThread(nullptr, 0, InitThread, nullptr, 0, nullptr);
        break;
    }
    return TRUE;
}
'''

# ================= БОТ =================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if await check_access(message.from_user.id):
        await message.answer(
            "👋 Привет! Я **ASI-Компилятор**.\n\n"
            "У тебя есть доступ! ✅\n"
            "Просто отправь мне файл `.js`, и я соберу для тебя `.asi` плагин.",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await message.answer(
            "⛔ **Доступ закрыт.**\n\n"
            "У вас нет прав для использования этого бота.\n"
            "Если у вас есть ключ доступа, используйте команду:\n"
            "`/key ВАШ_КЛЮЧ`",
            parse_mode=ParseMode.MARKDOWN
        )

@dp.message(Command("key"))
async def cmd_use_key(message: Message, command: CommandObject):
    user_id = message.from_user.id
    if await check_access(user_id):
        await message.answer("✅ У вас уже есть доступ!")
        return

    key_to_check = command.args
    if not key_to_check:
        await message.answer("⚠️ Пожалуйста, укажите ключ после команды. Пример:\n`/key 1a2b3c4d`", parse_mode=ParseMode.MARKDOWN)
        return

    async with aiosqlite.connect(DB_NAME) as db:
        # Ищем ключ
        async with db.execute("SELECT is_used FROM keys WHERE key_text = ?", (key_to_check,)) as cursor:
            row = await cursor.fetchone()
            
            if not row:
                await message.answer("❌ Неверный ключ!")
                return
            if row[0] == 1:
                await message.answer("❌ Этот ключ уже был использован кем-то другим!")
                return
            
            # Активируем ключ
            await db.execute("UPDATE keys SET is_used = 1, used_by = ? WHERE key_text = ?", (user_id, key_to_check))
            username = message.from_user.username or "Без юзернейма"
            await db.execute("INSERT OR REPLACE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
            await db.commit()

    await message.answer("🎉 **Успешно!** Ключ активирован. Теперь вы можете отправлять `.js` файлы для компиляции.", parse_mode=ParseMode.MARKDOWN)

# ================= АДМИН ПАНЕЛЬ =================
@dp.message(Command("genkey"))
async def cmd_genkey(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return # Игнорируем не админов

    try:
        count = int(command.args) if command.args else 1
    except ValueError:
        count = 1

    count = min(count, 20) # Максимум 20 ключей за раз
    generated_keys = []

    async with aiosqlite.connect(DB_NAME) as db:
        for _ in range(count):
            new_key = secrets.token_hex(6) # Генерирует ключ вида 4a8b9c1d2e3f
            await db.execute("INSERT INTO keys (key_text) VALUES (?)", (new_key,))
            generated_keys.append(f"`{new_key}`")
        await db.commit()

    keys_text = "\n".join(generated_keys)
    await message.answer(f"🔑 **Сгенерировано ключей ({count}):**\n\n{keys_text}", parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("users"))
async def cmd_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, username FROM users") as cursor:
            users = await cursor.fetchall()
            
    if not users:
        await message.answer("👥 Нет пользователей с доступом.")
        return
        
    text = "👥 **Пользователи с доступом:**\n\n"
    for uid, uname in users:
        text += f"ID: `{uid}` | @{uname}\n"
    
    await message.answer(text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("revoke"))
async def cmd_revoke(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return

    if not command.args:
        await message.answer("⚠️ Укажите ID пользователя. Пример: `/revoke 12345678`")
        return

    try:
        target_id = int(command.args)
    except ValueError:
        await message.answer("❌ ID должен быть числом.")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM users WHERE user_id = ?", (target_id,))
        await db.commit()

    await message.answer(f"🚫 Доступ у пользователя `{target_id}` отобран.", parse_mode=ParseMode.MARKDOWN)

# ================= ОБРАБОТЧИК ФАЙЛОВ =================
@dp.message(F.document)
async def handle_document(message: Message):
    if not await check_access(message.from_user.id):
        await message.answer("⛔ У вас нет доступа. Активируйте ключ командой `/key ВАШ_КЛЮЧ`")
        return

    if not message.document.file_name.endswith('.js'):
        await message.answer("⚠️ Пожалуйста, отправьте файл с расширением `.js`")
        return

    status_msg = await message.answer("🔄 Скачиваю файл...")
    temp_dir = tempfile.mkdtemp()
    js_path = os.path.join(temp_dir, "input.js")
    cpp_path = os.path.join(temp_dir, "source.cpp")
    asi_path = os.path.join(temp_dir, "gone_fix.asi")

    try:
        file_info = await bot.get_file(message.document.file_id)
        await bot.download_file(file_info.file_path, destination=js_path)
        await status_msg.edit_text("🔐 Шифрую JS-скрипт (XOR)...")

        with open(js_path, 'rb') as f:
            data = f.read()

        key_bytes = XOR_KEY.encode()
        encrypted = bytes(b ^ key_bytes[i % len(key_bytes)] for i, b in enumerate(data))
        
        lines = []
        for i in range(0, len(encrypted), 16):
            chunk = encrypted[i:i+16]
            hex_str = ', '.join(f'0x{b:02x}' for b in chunk)
            lines.append(f"    {hex_str},")
        array_str = '\n'.join(lines)

        source = EMBEDDED_ASI_CODE.replace("/* EMBED_JS_DATA_HERE */", array_str.strip())
        with open(cpp_path, 'w', encoding='utf-8') as f:
            f.write(source)

        await status_msg.edit_text("⚙️ Компилирую .asi файл под Windows...\n_(Это может занять пару секунд)_", parse_mode=ParseMode.MARKDOWN)

        compile_command = [
            COMPILER_CMD, "-shared", "-o", asi_path,
            "-std=c++17", "-s", "-O2", cpp_path,
            "-lws2_32", "-luser32", 
            "-static", "-static-libgcc", "-static-libstdc++" 
        ]

        process = await asyncio.create_subprocess_exec(
            *compile_command,
            cwd=temp_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode == 0 and os.path.exists(asi_path):
            file_size = os.path.getsize(asi_path)
            await status_msg.delete()
            document = FSInputFile(asi_path, filename=f"gone_fix_{datetime.now().strftime('%H%M%S')}.asi")
            await message.answer_document(
                document, 
                caption=f"✅ **Компиляция успешна!**\n📦 Размер файла: {file_size} байт",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            error_text = stderr.decode('utf-8', errors='ignore') or stdout.decode('utf-8', errors='ignore')
            await status_msg.edit_text(f"❌ **Ошибка компиляции!**\nКод: {process.returncode}\n\nЛог:\n`{error_text[:1000]}`", parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        await status_msg.edit_text(f"💥 **Внутренняя ошибка:**\n`{str(e)}`", parse_mode=ParseMode.MARKDOWN)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ================= ВЕБ СЕРВЕР ОБМАНКА =================
async def handle_ping(request):
    return web.Response(text="Бот компилятор работает!")

async def start_dummy_server():
    port = int(os.getenv("PORT", 8080))
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Веб-сервер запущен на порту {port}")

# ================= ЗАПУСК =================
async def main():
    await init_db()
    await start_dummy_server()
    print("Бот запущен. Ожидание сообщений...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
