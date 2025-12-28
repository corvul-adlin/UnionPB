import asyncio
import io
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from PIL import Image, ImageColor, ImageDraw
from aiohttp import web

# --- НАСТРОЙКИ (UnionPB 3.6) ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.getenv("PORT", 10000))

if not TOKEN or not CHANNEL_ID:
    print("ОШИБКА: Заполни BOT_TOKEN и CHANNEL_ID в настройках Render!")
    sys.exit(1)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ПАРАМЕТРЫ ХОЛСТА ---
CANVAS_SIZE = 1024
canvas = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), color='white')

# --- Вспомогательная функция для координат (ЛЕВЫЙ НИЖНИЙ УГОЛ) ---
def fix_y(y_user):
    """Преобразует Y из системы 'снизу-вверх' в систему Pillow 'сверху-вниз'."""
    return CANVAS_SIZE - 1 - int(y_user)

def get_emoji(color_name):
    """Подбирает эмодзи под цвет для вывода матрицы."""
    c = color_name.lower()
    mapping = {
        "black": "⬛", "white": "⬜", "red": "🟥", "blue": "🟦",
        "yellow": "🟨", "green": "🟩", "orange": "🟧", "purple": "🟪"
    }
    return mapping.get(c, "🟦")

# --- ФУНКЦИИ-ПОМОЩНИКИ (СОХРАНЕНЫ ИЗ 3.5) ---

async def load_last_canvas():
    """Загрузка последнего состояния из канала (бэкап)."""
    global canvas
    logging.info("Система: Ищу бэкап в канале...")
    try:
        async for message in bot.get_chat_history(CHANNEL_ID, limit=10):
            if message.document and message.document.file_name == "matrix.png":
                file_info = await bot.get_file(message.document.file_id)
                file_content = await bot.download_file(file_info.file_path)
                canvas = Image.open(file_content).convert('RGB')
                logging.info("✅ Успех! Прошлое полотно загружено.")
                return
        logging.warning("❓ Бэкап не найден.")
    except Exception as e:
        logging.error(f"Ошибка при загрузке: {e}")

async def backup_to_channel():
    """Тихий бэкап полотна в канал."""
    try:
        with io.BytesIO() as out:
            canvas.save(out, format="PNG")
            out.seek(0)
            file = types.BufferedInputFile(out.read(), filename="matrix.png")
            await bot.send_document(CHANNEL_ID, file, caption="UnionPB 3.6: Точка восстановления", disable_notification=True)
    except Exception as e:
        logging.error(f"Ошибка бэкапа: {e}")

# --- ОБРАБОТКА КОМАНД ---

@dp.message(Command("start", "help"))
async def send_help(message: types.Message):
    help_text = (
        "🎨 **UnionPB 3.6: Обновление координат!**\n\n"
        "Теперь `0 0` — это **ЛЕВЫЙ НИЖНИЙ УГОЛ**.\n\n"
        "**Команды:**\n"
        "`/add цвет x y` — поставить точку.\n"
        "Можно списком (каждая точка с новой строки).\n\n"
        "🔍 `/zoom x y` — рассмотреть область.\n"
        "🖼 `/view` — всё полотно целиком.\n"
        "🧹 `/fill цвет x1 y1 x2 y2` — залить область + матрица.\n"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("add"))
async def add_handler(message: types.Message):
    global canvas
    lines = message.text.split('\n')
    success = 0
    
    for i, line in enumerate(lines):
        parts = line.split()
        if i == 0: parts = parts[1:]
        if len(parts) != 3: continue
        
        try:
            color, x, y_raw = parts[0], int(parts[1]), int(parts[2])
            y = fix_y(y_raw) # Применяем новую систему координат
            
            if 0 <= x < CANVAS_SIZE and 0 <= y < CANVAS_SIZE:
                canvas.putpixel((x, y), ImageColor.getrgb(color))
                success += 1
        except: continue

    if success > 0:
        with io.BytesIO() as out:
            canvas.save(out, format="PNG")
            out.seek(0)
            photo = types.BufferedInputFile(out.read(), filename="update.png")
            await message.answer_photo(photo=photo, caption=f"✅ UnionPB 3.6: Отрисовано {success} точек (отсчет снизу).")
        asyncio.create_task(backup_to_channel())
    else:
        await message.answer("❌ Ошибка координат или цвета!")

@dp.message(Command("fill"))
async def fill_handler(message: types.Message):
    """Заливка области и вывод матрицы."""
    try:
        p = message.text.split()
        color = p[1]
        x1, y1_raw = int(p[2]), int(p[3])
        x2, y2_raw = int(p[4]), int(p[5])
        
        # Пересчитываем координаты для Pillow
        y1, y2 = fix_y(y1_raw), fix_y(y2_raw)
        
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)], fill=ImageColor.getrgb(color))
        
        # Генерируем матрицу (визуальное подтверждение)
        em = get_emoji(color)
        matrix_row = em * 8
        matrix_text = (matrix_row + "\n") * 5
        
        await message.answer(f"✅ Область {color} залита!\n\n**Матрица заполнения:**\n{matrix_text}", parse_mode="Markdown")
        asyncio.create_task(backup_to_channel())
    except Exception as e:
        await message.answer(f"Ошибка /fill: {e}")

@dp.message(Command("zoom"))
async def zoom_handler(message: types.Message):
    """Зум с учетом новой системы координат."""
    try:
        p = message.text.split()
        cx, cy_raw = int(p[1]), int(p[2])
        cy = fix_y(cy_raw)
        size = 50
        
        box = (max(0, cx-size), max(0, cy-size), min(CANVAS_SIZE, cx+size), min(CANVAS_SIZE, cy+size))
        cropped = canvas.crop(box)
        zoomed = cropped.resize((500, 500), resample=Image.NEAREST)
        
        with io.BytesIO() as out:
            zoomed.save(out, format="PNG")
            out.seek(0)
            await message.answer_photo(photo=types.BufferedInputFile(out.read(), filename="z.png"), caption=f"🔍 Зум {cx}:{cy_raw}")
    except:
        await message.answer("Ошибка! `/zoom x y`")

@dp.message(Command("view"))
async def view_handler(message: types.Message):
    with io.BytesIO() as out:
        canvas.save(out, format="PNG")
        out.seek(0)
        await message.answer_photo(photo=types.BufferedInputFile(out.read(), filename="c.png"), caption="🖼 UnionPB 3.6 Полотно")

# --- СЕРВЕР (ДЛЯ RENDER) ---
async def handle_ping(request):
    return web.Response(text="UnionPB 3.6 Engine: Online")

async def main():
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    
    await load_last_canvas()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())