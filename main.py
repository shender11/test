import asyncio
import os
import json
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart

import gspread
from google.oauth2.service_account import Credentials

# 🔴 SETTINGS (CHANGE THESE)
ADMIN_ID = 444097934
OWNER_ID = 1826030998
TEAM_NAME = "test"
TOKEN = "8697726930:AAFIPp8AktdwjdwEX-G3J6xXwZxxkmenCUU"

TEAM_SIZE = 15
ACTIVE_TEAM_SIZE = TEAM_SIZE - 2
MAX_DAY_OFF = max(1, int(ACTIVE_TEAM_SIZE * 0.2))

# Google access
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_json = os.getenv("GOOGLE_CREDENTIALS")
if not creds_json:
    raise Exception("GOOGLE_CREDENTIALS not found")

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
        [KeyboardButton(text="Start Break")],
        [KeyboardButton(text="End Break")]
    ],
    resize_keyboard=True
)

# START
@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Break tracking bot", reply_markup=keyboard)

# 🚨 CONTROL SYSTEM
async def break_control(user_id, minutes, name, username):

    # ⏳ 3 min before end
    if minutes > 3:
        await asyncio.sleep((minutes - 3) * 60)

        if user_id in break_data:
            await bot.send_message(
                user_id,
                "⏳ 3 minutes left until break ends"
            )

        await asyncio.sleep(3 * 60)
    else:
        await asyncio.sleep(minutes * 60)

    # 🚨 +1 min overdue
    await asyncio.sleep(60)

    if user_id in break_data:
        text = (
            f"[{TEAM_NAME}]\n"
            f"🚨 BREAK OVERDUE (+1 min)\n"
            f"{name}\n"
            f"@{username if username else 'no username'}"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        await bot.send_message(
            user_id,
            "🚨 You are 1 minute late!"
        )

    # 🚨 +3 min
    await asyncio.sleep(2 * 60)

    if user_id in break_data:
        await bot.send_message(
            user_id,
            "🚨 You are already 3 minutes late!"
        )

    # 🚨 +5 min
    await asyncio.sleep(2 * 60)

    if user_id in break_data:
        await bot.send_message(
            user_id,
            "🚨 You are already 5 minutes late!"
        )

    # 🔁 every 5 minutes
    while user_id in break_data:
        await asyncio.sleep(5 * 60)

        if user_id in break_data:
            await bot.send_message(
                user_id,
                "🚨 You are still on break! Return to work!"
            )

# MAIN LOGIC
@dp.message()
async def handle(message: Message):
    user_id = message.from_user.id

    # START BREAK
    if message.text == "Start Break":
        waiting_time.add(user_id)
        await message.answer("Enter break duration in minutes (max 30)")

    # INPUT TIME
    elif user_id in waiting_time:

        if not message.text.isdigit():
            await message.answer("❗ Enter a number (example: 15)")
            return

        minutes = int(message.text)

        if minutes > 30:
            await message.answer("❗ Maximum is 30 minutes")
            return

        if minutes <= 0:
            await message.answer("❗ Invalid value")
            return

        waiting_time.remove(user_id)

        break_data[user_id] = {
            "start": datetime.now(),
            "minutes": minutes
        }

        await message.answer(f"Break started for {minutes} min", reply_markup=keyboard)

        text = (
            f"[{TEAM_NAME}]\n"
            f"🟡 Break started ({minutes} min)\n"
            f"{message.from_user.full_name}\n"
            f"@{message.from_user.username if message.from_user.username else 'no username'}"
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

    # END BREAK
    elif message.text == "End Break":

        if user_id not in break_data:
            await message.answer("No active break")
            return

        data = break_data[user_id]

        now = datetime.now()
        start_time = data["start"]
        duration = now - start_time
        minutes = int(duration.total_seconds() // 60)

        sheet.append_row([
            now.strftime("%d.%m.%Y"),
            message.from_user.full_name,
            message.from_user.username or "no username",
            start_time.strftime("%H:%M:%S"),
            now.strftime("%H:%M:%S"),
            minutes
        ])

        text = (
            f"[{TEAM_NAME}]\n"
            f"🟢 Break ended\n"
            f"{message.from_user.full_name}\n"
            f"⏱ {minutes} min"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        del break_data[user_id]

        await message.answer("Break finished", reply_markup=keyboard)

    elif message.text == "Take day off":
        waiting_dayoff.add(user_id)
        await message.answer("Write date DD.MM (example 25.04)")

    elif user_id in waiting_dayoff:

        try:
            day, month = map(int, message.text.split("."))
            year = datetime.now().year
            selected_date = datetime(year, month, day)
        except:
            await message.answer("Wrong format. Example: 25.04")
            return

        waiting_dayoff.remove(user_id)

        records = days_off_sheet.get_all_values()
        user_id_str = str(user_id)

        user_days = [
            r for r in records
            if len(r) > 5 and r[3] == user_id_str and r[5] == str(month)
        ]

        if len(user_days) >= 6:
            await message.answer("You already have 6 days off this month")
            return

        same_day = [
            r for r in records
            if len(r) > 6 and r[4] == selected_date.strftime("%d.%m.%Y")
        ]

        if len(same_day) >= MAX_DAY_OFF:
            await message.answer("This day is already full")
            return

        days_off_sheet.append_row([
            datetime.now().strftime("%d.%m.%Y"),
            message.from_user.full_name,
            message.from_user.username or "no username",
            user_id,
            selected_date.strftime("%d.%m.%Y"),
            month,
            TEAM_NAME
        ])

        remaining = MAX_DAY_OFF - len(same_day) - 1

        text = (
            f"[{TEAM_NAME}]\n"
            f"📅 Day off taken\n"
            f"{message.from_user.full_name}\n"
            f"Date: {selected_date.strftime('%d.%m.%Y')}\n"
            f"Remaining spots: {remaining}"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        await message.answer("Day off saved")

    elif message.text == "My days off":

        records = days_off_sheet.get_all_values()
        user_id_str = str(user_id)
        month = datetime.now().month

        user_days = [
            r for r in records
            if len(r) > 5 and r[3] == user_id_str and int(r[5]) == month
        ]

        if not user_days:
            await message.answer("No days off this month")
            return

        text = "Your days off:\n\n"

        for r in user_days:
            text += f"{r[4]}\n"

        text += f"\nRemaining: {6 - len(user_days)}"

        await message.answer(text)

# RUN
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
