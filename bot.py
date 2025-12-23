import asyncio
import io
import logging
import os
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from PIL import Image, ImageColor, ImageDraw
from aiohttp import web

# --- НАСТРОЙКИ (Берем данные из настроек Render) ---
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.getenv("PORT", 10000))

# Проверка: если ты забыл вписать токен в Render, бот сразу скажет об этом
if not TOKEN or not CHANNEL_ID:
    print("ОШИБКА: Заполни BOT_TOKEN и CHANNEL_ID в настройках Render (раздел Environment)!")
    sys.exit(1)

# Инициализируем движок бота
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ПАРАМЕТРЫ ХОЛСТА ---
# 1024x1024 — это золотая середина. Картинка весит немного, памяти ест мало.
CANVAS_SIZE = 1024
# Создаем пустой белый холст в оперативной памяти
canvas = Image.new('RGB', (CANVAS_SIZE, CANVAS_SIZE), color='white')

# --- ФУНКЦИИ-ПОМОЩНИКИ (ИНЖЕНЕРНАЯ ЧАСТЬ) ---

async def load_last_canvas():
    """Эта функция срабатывает один раз при включении бота. 
    Она идет в твой канал и ищет последнюю сохраненную картинку."""
    global canvas
    logging.info("Система: Ищу бэкап в канале...")
    try:
        async for message in bot.get_chat_history(CHANNEL_ID, limit=10):
            if message.document and message.document.file_name == "matrix.png":
                # Скачиваем файл из Телеграма прямо в память
                file_info = await bot.get_file(message.document.file_id)
                file_content = await bot.download_file(file_info.file_path)
                # Обновляем наш холст тем, что нашли
                canvas = Image.open(file_content).convert('RGB')
                logging.info("✅ Успех! Прошлое полотно загружено.")
                return
        logging.warning("❓ Бэкап не найден, начинаем с чистого листа.")
    except Exception as e:
        logging.error(f"Ошибка при загрузке: {e}")

async def backup_to_channel():
    """Отправляет текущее состояние картинки в канал 'про запас'."""
    try:
        with io.BytesIO() as out:
            canvas.save(out, format="PNG")
            out.seek(0)
            file = types.BufferedInputFile(out.read(), filename="matrix.png")
            # Мы отправляем файл в канал тихо, чтобы не спамить уведомлениями
            await bot.send_document(CHANNEL_ID, file, caption="Точка восстановления системы", disable_notification=True)
    except Exception as e:
        logging.error(f"Ошибка бэкапа: {e}")

# --- ОБРАБОТКА КОМАНД ПОЛЬЗОВАТЕЛЕЙ ---

@dp.message(Command("start", "help"))
async def send_help(message: types.Message):
    """Красивое описание команд для тебя и друзей."""
    help_text = (
        "🎨 **Добро пожаловать в Pixel Battle!**\n\n"
        "**Как рисовать:**\n"
        "`/add цвет x y` — поставить одну точку.\n"
        "Можно прислать список точек (каждая с новой строки), чтобы рисовать быстрее:\n"
        "`/add red 100 100` \n"
        "`blue 101 100` \n"
        "`green 102 100` \n\n"
        "**Инструменты:**\n"
        "🔍 `/zoom x y` — рассмотреть область вблизи (центр в x y)\n"
        "🖼 `/view` — посмотреть всё полотно целиком\n"
        "🧹 `/fill цвет x1 y1 x2 y2` — залить прямоугольник\n\n"
        f"📏 Размер поля: {CANVAS_SIZE}x{CANVAS_SIZE} пикселей."
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("add"))
async def add_handler(message: types.Message):
    """Команда для рисования точек (одной или многих)."""
    global canvas
    lines = message.text.split('\n') # Разбиваем сообщение на строчки
    
    success = 0
    # Проходим по каждой строчке сообщения
    for i, line in enumerate(lines):
        parts = line.split()
        # Для первой строки убираем само слово '/add'
        if i == 0: parts = parts[1:]
        
        if len(parts) != 3: continue # Если в строке не 3 элемента (цвет x y), пропускаем её
        
        try:
            color, x, y = parts[0], int(parts[1]), int(parts[2])
            if 0 <= x < CANVAS_SIZE and 0 <= y < CANVAS_SIZE:
                # Рисуем пиксель
                canvas.putpixel((x, y), ImageColor.getrgb(color))
                success += 1
        except:
            continue

    if success > 0:
        # Сразу готовим картинку для ответа пользователю
        with io.BytesIO() as out:
            canvas.save(out, format="PNG")
            out.seek(0)
            photo = types.BufferedInputFile(out.read(), filename="update.png")
            await message.answer_photo(photo=photo, caption=f"✅ Готово! Нарисовано точек: {success}")
        
        # Запускаем сохранение в канал в фоновом режиме, чтобы бот не «тупил»
        asyncio.create_task(backup_to_channel())
    else:
        await message.answer("❌ Ошибка! Используй: `/add red 50 50` (и проверь координаты)")

@dp.message(Command("fill"))
async def fill_handler(message: types.Message):
    """Команда для заливки области (квадрата/прямоугольника)."""
    try:
        # Пример: /fill red 10 10 50 50
        p = message.text.split()
        color, x1, y1, x2, y2 = p[1], int(p[2]), int(p[3]), int(p[4]), int(p[5])
        
        # Инструмент для рисования фигур
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([x1, y1, x2, y2], fill=ImageColor.getrgb(color))
        
        await message.answer(f"🟦 Область закрашена цветом {color}")
        asyncio.create_task(backup_to_channel())
    except:
        await message.answer("Ошибка! Формат: `/fill цвет x1 y1 x2 y2`")

@dp.message(Command("zoom"))
async def zoom_handler(message: types.Message):
    """Увеличение куска карты."""
    try:
        p = message.text.split()
        cx, cy = int(p[1]), int(p[2])
        size = 50 # Радиус захвата
        
        # Вырезаем квадрат вокруг указанных координат
        box = (max(0, cx-size), max(0, cy-size), min(CANVAS_SIZE, cx+size), min(CANVAS_SIZE, cy+size))
        cropped = canvas.crop(box)
        # Увеличиваем в 10 раз, чтобы пиксели были огромными и четкими
        zoomed = cropped.resize((500, 500), resample=Image.NEAREST)
        
        with io.BytesIO() as out:
            zoomed.save(out, format="PNG")
            out.seek(0)
            photo = types.BufferedInputFile(out.read(), filename="zoom.png")
            await message.answer_photo(photo=photo, caption=f"🔍 Сектор вокруг {cx}:{cy}")
    except:
        await message.answer("Ошибка! Используй: `/zoom 100 100`")

@dp.message(Command("view"))
async def view_handler(message: types.Message):
    """Показать всё поле."""
    with io.BytesIO() as out:
        canvas.save(out, format="PNG")
        out.seek(0)
        photo = types.BufferedInputFile(out.read(), filename="canvas.png")
        await message.answer_photo(photo=photo, caption="🖼 Текущее состояние всего поля")

# --- СЕРВЕР ДЛЯ ПОДДЕРЖКИ ЖИЗНИ (КРОН / RENDER) ---

async def handle_ping(request):
    """Этот адрес будет дергать Cron-job, чтобы Render не заснул."""
    return web.Response(text="Pixel Battle Engine: Online")

async def main():
    # Настройка логов (чтобы в панели Render было видно, что происходит)
    logging.basicConfig(level=logging.INFO)
    
    # Запуск веб-сервера
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    
    # Пытаемся восстановить полотно из канала
    await load_last_canvas()
    
    # Запускаем чтение сообщений
    await dp.start_polling(bot)

if __name__ == "__main__":
    # Запуск всей системы
    asyncio.run(main())