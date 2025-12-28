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

# --- CONFIG ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.getenv("PORT", 10000))

if not TOKEN or not CHANNEL_ID:
    logging.critical("CRITICAL ERROR: Environment variables missing!")
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

CANVAS_SIZE = 1024
canvas = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), color='white')

# --- ENGINE MATH ---
def fix_y(y_user):
    """Bottom-left coordinate system transform."""
    return CANVAS_SIZE - 1 - int(y_user)

def get_emoji(color_name):
    mapping = {
        "black": "⬛", "white": "⬜", "red": "🟥", "blue": "🟦",
        "yellow": "🟨", "green": "🟩", "orange": "🟧", "purple": "🟪"
    }
    return mapping.get(color_name.lower(), "🟦")

# --- DATABASE / BACKUP ---
async def load_last_canvas():
    global canvas
    try:
        async for message in bot.get_chat_history(CHANNEL_ID, limit=10):
            if message.document and message.document.file_name == "matrix.png":
                file_info = await bot.get_file(message.document.file_id)
                file_content = await bot.download_file(file_info.file_path)
                canvas = Image.open(file_content).convert('RGB')
                return
    except Exception as e:
        logging.error(f"Load error: {e}")

async def backup_to_channel():
    try:
        with io.BytesIO() as out:
            canvas.save(out, format="PNG")
            out.seek(0)
            file = types.BufferedInputFile(out.read(), filename="matrix.png")
            await bot.send_document(CHANNEL_ID, file, caption="UnionPB 3.7 Auto-Backup", disable_notification=True)
    except Exception as e:
        logging.error(f"Backup error: {e}")

# --- HANDLERS ---

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
        await message.answer(f"✅ Добавлено пикселей: {success}")

@dp.message(Command("line"))
async def line_handler(message: types.Message):
    """Draws a line between two points."""
    try:
        p = message.text.split()
        color = p[1]
        x1, y1 = int(p[2]), fix_y(p[3])
        x2, y2 = int(p[4]), fix_y(p[5])
        
        draw = ImageDraw.Draw(canvas)
        draw.line([x1, y1, x2, y2], fill=ImageColor.getrgb(color), width=1)
        
        await message.answer(f"📏 Линия ({color}) проведена!")
        asyncio.create_task(backup_to_channel())
    except Exception as e:
        await message.answer("Ошибка! `/line color x1 y1 x2 y2`")

@dp.message(Command("circle"))
async def circle_handler(message: types.Message):
    """Draws an empty circle."""
    try:
        p = message.text.split()
        color, cx, cy_raw, r = p[1], int(p[2]), int(p[3]), int(p[4])
        cy = fix_y(cy_raw)
        
        draw = ImageDraw.Draw(canvas)
        draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=ImageColor.getrgb(color))
        
        await message.answer(f"⭕ Окружность ({color}) готова!")
        asyncio.create_task(backup_to_channel())
    except:
        await message.answer("Ошибка! `/circle color x y radius`")

@dp.message(Command("point"))
async def point_handler(message: types.Message):
    """Get color of a specific pixel."""
    try:
        p = message.text.split()
        x, y_raw = int(p[1]), int(p[2])
        y = fix_y(y_raw)
        rgb = canvas.getpixel((x, y))
        await message.answer(f"📍 Точка {x}:{y_raw}\nЦвет (RGB): `{rgb}`")
    except:
        await message.answer("Ошибка! `/point x y`")

@dp.message(Command("fill"))
async def fill_handler(message: types.Message):
    try:
        p = message.text.split()
        color = p[1]
        x1, y1, x2, y2 = int(p[2]), fix_y(p[3]), int(p[4]), fix_y(p[5])
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], fill=ImageColor.getrgb(color))
        
        em = get_emoji(color)
        await message.answer(f"✅ Заливка {em} завершена!")
        asyncio.create_task(backup_to_channel())
    except:
        await message.answer("Ошибка! `/fill color x1 y1 x2 y2`")

@dp.message(Command("zoom"))
async def zoom_handler(message: types.Message):
    try:
        p = message.text.split()
        cx, cy = int(p[1]), fix_y(p[2])
        box = (max(0, cx-50), max(0, cy-50), min(CANVAS_SIZE, cx+50), min(CANVAS_SIZE, cy+50))
        zoomed = canvas.crop(box).resize((500, 500), resample=Image.NEAREST)
        with io.BytesIO() as out:
            zoomed.save(out, format="PNG")
            out.seek(0)
            await message.answer_photo(photo=types.BufferedInputFile(out.read(), filename="z.png"))
    except:
        await message.answer("Ошибка зума!")

@dp.message(Command("view"))
async def view_handler(message: types.Message):
    with io.BytesIO() as out:
        canvas.save(out, format="PNG")
        out.seek(0)
        await message.answer_photo(photo=types.BufferedInputFile(out.read(), filename="c.png"))

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