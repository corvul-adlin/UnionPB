import asyncio
import io
import logging
import os
import sys
import math
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from PIL import Image, ImageColor, ImageDraw
from aiohttp import web

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.getenv("PORT", 10000))

if not TOKEN or not CHANNEL_ID:
    logging.critical("ОШИБКА: Проверь переменные BOT_TOKEN и CHANNEL_ID!")
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

CANVAS_SIZE = 1024
canvas = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), color='white')

# --- ИНЖЕНЕРНЫЕ ФУНКЦИИ ---

def fix_y(y_user):
    """Математика: переворачиваем Y, чтобы (0,0) был внизу слева."""
    return CANVAS_SIZE - 1 - int(y_user)

async def send_canvas_photo(message, caption):
    """Универсальная функция для отправки фото холста с текстом."""
    with io.BytesIO() as out:
        canvas.save(out, format="PNG")
        out.seek(0)
        photo = types.BufferedInputFile(out.read(), filename="update.png")
        await message.answer_photo(photo=photo, caption=caption)

async def load_last_canvas():
    """Загрузка последнего состояния из канала при перезапуске."""
    global canvas
    try:
        async for message in bot.get_chat_history(CHANNEL_ID, limit=10):
            if message.document and message.document.file_name == "matrix.png":
                file_info = await bot.get_file(message.document.file_id)
                file_content = await bot.download_file(file_info.file_path)
                canvas = Image.open(file_content).convert('RGB')
                return
    except Exception as e:
        logging.error(f"Ошибка загрузки бэкапа: {e}")

async def backup_to_channel():
    """Тихое сохранение холста в канал."""
    try:
        with io.BytesIO() as out:
            canvas.save(out, format="PNG")
            out.seek(0)
            file = types.BufferedInputFile(out.read(), filename="matrix.png")
            await bot.send_document(CHANNEL_ID, file, caption="UnionPB 3.7 Auto-Backup", disable_notification=True)
    except Exception as e:
        logging.error(f"Ошибка бэкапа: {e}")

# --- ТЕКСТОВЫЕ БЛОКИ ---
# Выносим команды в отдельную переменную, чтобы не дублировать код
COMMANDS_TEXT = (
    "**Доступные команды:**\n"
    "• `/add цвет x y` — поставить точку\n"
    "• `/line цвет x1 y1 x2 y2` — провести линию\n"
    "• `/circle цвет x y r` — нарисовать круг\n"
    "• `/fill цвет x1 y1 x2 y2` — залить область\n"
    "• `/zoom x y` — увеличить сектор 50x50 пикселей\n"
    "• `/view` — показать всё полотно целиком"
)

# --- ОБРАБОТЧИКИ КОМАНД ---

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    """Приветствие + Команды"""
    welcome_text = (
        "🚀 **UnionPB v3.7 запущен!**\n\n"
        "Я готов рисовать. Координаты (0,0) — **снизу слева**.\n\n"
    )
    await message.answer(welcome_text + COMMANDS_TEXT, parse_mode="Markdown")

@dp.message(Command("help"))
async def help_handler(message: types.Message):
    """Только список команд без приветствия"""
    await message.answer(COMMANDS_TEXT, parse_mode="Markdown")

@dp.message(Command("add"))
async def add_handler(message: types.Message):
    lines = message.text.split('\n')
    success = 0
    for i, line in enumerate(lines):
        parts = line.split()
        if i == 0: parts = parts[1:]
        if len(parts) != 3: continue
        try:
            color, x, y_raw = parts[0], int(parts[1]), int(parts[2])
            y = fix_y(y_raw)
            if 0 <= x < CANVAS_SIZE and 0 <= y < CANVAS_SIZE:
                canvas.putpixel((x, y), ImageColor.getrgb(color))
                success += 1
        except: continue
    
    if success > 0:
        asyncio.create_task(backup_to_channel())
        await send_canvas_photo(message, f"✅ Добавлено пикселей: {success}")
    else:
        await message.answer("❌ Ошибка ввода! Пример: `/add red 500 500`")

@dp.message(Command("line"))
async def line_handler(message: types.Message):
    try:
        p = message.text.split()
        color, x1, y1_r, x2, y2_r = p[1], int(p[2]), int(p[3]), int(p[4]), int(p[5])
        draw = ImageDraw.Draw(canvas)
        draw.line([x1, fix_y(y1_r), x2, fix_y(y2_r)], fill=ImageColor.getrgb(color), width=1)
        asyncio.create_task(backup_to_channel())
        await send_canvas_photo(message, f"📏 Линия ({color}) проведена!")
    except:
        await message.answer("Ошибка! `/line color x1 y1 x2 y2`")

@dp.message(Command("circle"))
async def circle_handler(message: types.Message):
    try:
        p = message.text.split()
        color, cx, cy_r, r = p[1], int(p[2]), int(p[3]), int(p[4])
        cy = fix_y(cy_r)
        draw = ImageDraw.Draw(canvas)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=ImageColor.getrgb(color))
        asyncio.create_task(backup_to_channel())
        await send_canvas_photo(message, f"⭕ Окружность ({color}) готова!")
    except:
        await message.answer("Ошибка! `/circle color x y radius`")

@dp.message(Command("fill"))
async def fill_handler(message: types.Message):
    try:
        p = message.text.split()
        color, x1, y1_r, x2, y2_r = p[1], int(p[2]), int(p[3]), int(p[4]), int(p[5])
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([min(x1, x2), min(fix_y(y1_r), fix_y(y2_r)), max(x1, x2), max(fix_y(y1_r), fix_y(y2_r))], fill=ImageColor.getrgb(color))
        asyncio.create_task(backup_to_channel())
        await send_canvas_photo(message, f"✅ Область залита цветом {color}!")
    except:
        await message.answer("Ошибка! `/fill color x1 y1 x2 y2`")

@dp.message(Command("view"))
async def view_handler(message: types.Message):
    await send_canvas_photo(message, "🖼 Текущее состояние UnionPB")

@dp.message(Command("zoom"))
async def zoom_handler(message: types.Message):
    """Увеличение области с подсказкой при ошибке"""
    try:
        p = message.text.split()
        if len(p) != 3:
            raise ValueError("Неверное количество аргументов")
            
        cx, cy_raw = int(p[1]), int(p[2])
        cy = fix_y(cy_raw)
        
        box = (max(0, cx-50), max(0, cy-50), min(CANVAS_SIZE, cx+50), min(CANVAS_SIZE, cy+50))
        zoomed = canvas.crop(box).resize((500, 500), resample=Image.NEAREST)
        
        with io.BytesIO() as out:
            zoomed.save(out, format="PNG")
            out.seek(0)
            await message.answer_photo(photo=types.BufferedInputFile(out.read(), filename="z.png"), caption=f"🔍 Зум {cx}:{cy_raw}")
    except:
        await message.answer("❌ Ошибка зума! Используй: `/zoom x y` (например: `/zoom 512 512`)")

# --- ЗАПУСК ---

async def main():
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="UnionPB 3.7 Online"))
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    
    await load_last_canvas()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())