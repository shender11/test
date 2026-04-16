import asyncio
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

import gspread
from google.oauth2.service_account import Credentials

# 🔴 НАСТРОЙКИ
ADMIN_ID = 444097934
OWNER_ID = 1826030998
TEAM_NAME = "test"
TOKEN = "8697726930:AAFIPp8AktdwjdwEX-G3J6xXwZxxkmenCUU"

TEAM_SIZE = 15
ACTIVE_TEAM_SIZE = TEAM_SIZE - 2
MAX_DAY_OFF = max(1, int(ACTIVE_TEAM_SIZE * 0.2))

# Google доступ
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")
if not creds_json:
    raise Exception("GOOGLE_CREDENTIALS не найден")

creds_dict = json.loads(creds_json)

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

sheet = client.open_by_key("1UtE6yC0Wz0lYFlTcdDqWu1brarxkkqRaUITHg9Ynlt8").sheet1
days_off_sheet = client.open_by_key("1UtE6yC0Wz0lYFlTcdDqWu1brarxkkqRaUITHg9Ynlt8").worksheet("DaysOff")

bot = Bot(token=TOKEN)
dp = Dispatcher()

break_data = {}
waiting_dayoff = set()
waiting_time = set()

keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Начать перерыв")],
        [KeyboardButton(text="Закончить перерыв")],
        [KeyboardButton(text="Взять выходной")],
        [KeyboardButton(text="Мои выходные")]
    ],
    resize_keyboard=True
)

# СТАРТ
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Бот учета перерывов и выходных", reply_markup=keyboard)

# 🚨 КОНТРОЛЬ ПЕРЕРЫВА
async def break_control(user_id, minutes, name, username):

    if minutes > 3:
        await asyncio.sleep((minutes - 3) * 60)

        if user_id in break_data:
            await bot.send_message(user_id, "⏳ До конца перерыва осталось 3 минуты")

        await asyncio.sleep(3 * 60)
    else:
        await asyncio.sleep(minutes * 60)

    await asyncio.sleep(60)

    if user_id in break_data:
        text = (
            f"[{TEAM_NAME}]\n"
            f"🚨 ОПОЗДАНИЕ (+1 мин)\n"
            f"{name}\n"
            f"@{username if username else 'без username'}"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)
        await bot.send_message(user_id, "🚨 Ты опоздал на 1 минуту!")

    await asyncio.sleep(2 * 60)

    if user_id in break_data:
        await bot.send_message(user_id, "🚨 Ты уже опаздываешь на 3 минуты!")

    await asyncio.sleep(2 * 60)

    if user_id in break_data:
        await bot.send_message(user_id, "🚨 Ты уже опаздываешь на 5 минут!")

    while user_id in break_data:
        await asyncio.sleep(5 * 60)

        if user_id in break_data:
            await bot.send_message(user_id, "🚨 Ты всё ещё на перерыве! Вернись к работе!")

# ОСНОВНАЯ ЛОГИКА
@dp.message()
async def handle(message: Message):
    user_id = message.from_user.id

    if message.text == "Начать перерыв":
        waiting_time.add(user_id)
        await message.answer("Введи длительность перерыва (максимум 30 минут)")

    elif user_id in waiting_time:

        if not message.text.isdigit():
            await message.answer("❗ Введи число (например: 15)")
            return

        minutes = int(message.text)

        if minutes > 30:
            await message.answer("❗ Максимум 30 минут")
            return

        if minutes <= 0:
            await message.answer("❗ Некорректное значение")
            return

        waiting_time.remove(user_id)

        break_data[user_id] = {
            "start": datetime.now(),
            "minutes": minutes
        }

        await message.answer(f"Перерыв начат на {minutes} мин", reply_markup=keyboard)

        text = (
            f"[{TEAM_NAME}]\n"
            f"🟡 Начал перерыв ({minutes} мин)\n"
            f"{message.from_user.full_name}"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        asyncio.create_task(
            break_control(
                user_id,
                minutes,
                message.from_user.full_name,
                message.from_user.username
            )
        )

    elif message.text == "Закончить перерыв":

        if user_id not in break_data:
            await message.answer("Нет активного перерыва")
            return

        data = break_data[user_id]

        now = datetime.now()
        start_time = data["start"]
        duration = now - start_time
        minutes = int(duration.total_seconds() // 60)

        sheet.append_row([
            now.strftime("%d.%m.%Y"),
            message.from_user.full_name,
            message.from_user.username or "без username",
            start_time.strftime("%H:%M:%S"),
            now.strftime("%H:%M:%S"),
            minutes
        ])

        text = (
            f"[{TEAM_NAME}]\n"
            f"🟢 Закончил перерыв\n"
            f"{message.from_user.full_name}\n"
            f"{minutes} мин"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        del break_data[user_id]

        await message.answer("Перерыв завершён", reply_markup=keyboard)

    elif message.text == "Взять выходной":
        waiting_dayoff.add(user_id)
        await message.answer("Напиши дату в формате ДД.ММ (пример 25.04)")

    elif user_id in waiting_dayoff:

        try:
            day, month = map(int, message.text.split("."))
            year = datetime.now().year
            selected_date = datetime(year, month, day)
        except:
            await message.answer("Неверный формат. Пример: 25.04")
            return

        waiting_dayoff.remove(user_id)

        records = days_off_sheet.get_all_values()
        user_id_str = str(user_id)

        user_days = [
            r for r in records
            if len(r) > 5 and r[3] == user_id_str and r[5] == str(month)
        ]

        if len(user_days) >= 6:
            await message.answer("У тебя уже 6 выходных в этом месяце")
            return

        same_day = [
            r for r in records
            if len(r) > 6 and r[4] == selected_date.strftime("%d.%m.%Y")
        ]

        if len(same_day) >= MAX_DAY_OFF:
            await message.answer("На этот день уже нет мест")
            return

        days_off_sheet.append_row([
            datetime.now().strftime("%d.%m.%Y"),
            message.from_user.full_name,
            message.from_user.username or "без username",
            user_id,
            selected_date.strftime("%d.%m.%Y"),
            month,
            TEAM_NAME
        ])

        remaining = MAX_DAY_OFF - len(same_day) - 1

        text = (
            f"[{TEAM_NAME}]\n"
            f"📅 Взял выходной\n"
            f"{message.from_user.full_name}\n"
            f"Дата: {selected_date.strftime('%d.%m.%Y')}\n"
            f"Осталось мест: {remaining}"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        await message.answer("Выходной сохранён")

    elif message.text == "Мои выходные":

        records = days_off_sheet.get_all_values()
        user_id_str = str(user_id)
        month = datetime.now().month

        user_days = [
            r for r in records
            if len(r) > 5 and r[3] == user_id_str and int(r[5]) == month
        ]

        if not user_days:
            await message.answer("У тебя нет выходных в этом месяце")
            return

        text = "Твои выходные:\n\n"

        for r in user_days:
            text += f"{r[4]}\n"

        text += f"\nОсталось: {6 - len(user_days)}"

        await message.answer(text)

# ЗАПУСК
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
