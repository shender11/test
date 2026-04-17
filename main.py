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
waiting_time = set()
users = set()
calendar_messages = {}
last_messages = {}
blocked_users = set()
salary_waiting = {}

# 🔹 ГЛАВНОЕ МЕНЮ
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Перерывы")],
        [KeyboardButton(text="Выходные")],
        [KeyboardButton(text="Зарплата")]
    ],
    resize_keyboard=True
)

# 🔹 ПЕРЕРЫВЫ
break_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Начать перерыв")],
        [KeyboardButton(text="Закончить перерыв")],
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True
)

# 🔹 ВЫХОДНЫЕ
days_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Взять выходной")],
        [KeyboardButton(text="Мои выходные")],
        [KeyboardButton(text="Свободные дни")],
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True
)

# 🔹 ЗАРПЛАТА
salary_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Моя зарплата")],
        [KeyboardButton(text="Назад")]
    ],
    resize_keyboard=True
)

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import CallbackQuery
from aiogram import F

def generate_calendar():
    now = datetime.now()
    month = now.month
    year = now.year

    records = days_off_sheet.get_all_values()
    buttons = []

    for day in range(1, 32):
        try:
            date = datetime(year, month, day)
        except:
            continue

        date_str = date.strftime("%d.%m.%Y")

        same_day = [
            r for r in records
            if len(r) > 5 and r[4] == date_str
        ]

        taken = len(same_day)

        if date.date() < now.date():
            text = f"⛔ {day}"
            callback = "ignore"
        else:
            if taken >= MAX_DAY_OFF:
                text = f"🔴 {day}"
                callback = "ignore"
            else:
                left = MAX_DAY_OFF - taken
                text = f"{day}🟢{left}"
                callback = f"day_{day}_{month}"

        buttons.append(
            InlineKeyboardButton(
                text=text,
                callback_data=callback
            )
        )

    keyboard = [buttons[i:i+5] for i in range(0, len(buttons), 5)]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

async def send_clean_message(user_id, text, reply_markup=None):

    # ❌ удалить старый календарь
    if user_id in calendar_messages:
        try:
            await bot.delete_message(
                chat_id=user_id,
                message_id=calendar_messages[user_id]
            )
        except:
            pass

        del calendar_messages[user_id]

    # ❌ удалить старое сообщение
    if user_id in last_messages:
        try:
            await bot.delete_message(
                chat_id=user_id,
                message_id=last_messages[user_id]
            )
        except:
            pass

    # ✅ отправить новое
    msg = await bot.send_message(
        user_id,
        text,
        reply_markup=reply_markup
    )

    # сохранить id
    last_messages[user_id] = msg.message_id

    return msg

# СТАРТ
@dp.message(CommandStart())
async def start(message: Message):
    await send_clean_message(
        message.from_user.id,
        "Главное меню",
        reply_markup=main_keyboard
    )

# 🚨 КОНТРОЛЬ ПЕРЕРЫВА
async def break_control(user_id, minutes, name, username):
    
    if user_id in blocked_users:
        return

    if minutes > 3:
        await asyncio.sleep((minutes - 3) * 60)

        if user_id in break_data and user_id not in blocked_users:
            await bot.send_message(user_id, "⏳ До конца перерыва осталось 3 минуты")

        await asyncio.sleep(3 * 60)
    else:
        await asyncio.sleep(minutes * 60)

    await asyncio.sleep(60)

    if user_id in break_data and user_id not in blocked_users:
        text = (
            f"🚨 ОПОЗДАНИЕ (+1 мин)\n"
            f"{name}\n"
            f"@{username if username else 'без username'}"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)
        await bot.send_message(user_id, "🚨 Ты опоздал на 1 минуту!")

    await asyncio.sleep(2 * 60)

    if user_id in break_data and user_id not in blocked_users:
        await bot.send_message(user_id, "🚨 Ты уже опаздываешь на 3 минуты!")

    await asyncio.sleep(2 * 60)

    if user_id in break_data and user_id not in blocked_users:
        await bot.send_message(user_id, "🚨 Ты уже опаздываешь на 5 минут!")

    while user_id in break_data:
        await asyncio.sleep(5 * 60)

        if user_id in break_data and user_id not in blocked_users:
            await bot.send_message(user_id, "🚨 Ты всё ещё на перерыве! Вернись к работе!")

# ОСНОВНАЯ ЛОГИКА
@dp.message()
async def handle(message: Message):

    user_id = message.from_user.id

    # 🔹 МЕНЮ
    if message.text == "Перерывы":
        await send_clean_message(user_id, "Меню перерывов", reply_markup=break_keyboard)
        return

    elif message.text == "Выходные":
        await send_clean_message(user_id, "Меню выходных", reply_markup=days_keyboard)
        return

    elif message.text == "Зарплата":
        await send_clean_message(user_id, "Меню зарплаты", reply_markup=salary_keyboard)
        return

    elif message.text == "Назад":
        await send_clean_message(user_id, "Главное меню", reply_markup=main_keyboard)
        return
        
    if message.text and message.text.startswith("/"):
        return
    
    if message.from_user.id in blocked_users:
        return
        
    if user_id not in users:
        users.add(user_id)

    if message.text == "Начать перерыв":
        waiting_time.add(user_id)
        await send_clean_message(user_id, "Введи длительность перерыва (максимум 30 минут)")

    elif user_id in waiting_time:

        if not message.text or not message.text.isdigit():
            await send_clean_message(user_id, "❗ Введи число")
            return

        minutes = int(message.text)

        if minutes > 30:
            await send_clean_message(user_id, "❗ Максимум 30 минут")
            return

        if minutes <= 0:
            await send_clean_message(user_id, "❗ Некорректное значение")
            return

        waiting_time.remove(user_id)

        break_data[user_id] = {
            "start": datetime.now(),
            "minutes": minutes
        }

        await send_clean_message(user_id, f"Перерыв начат на {minutes} мин", reply_markup=break_keyboard)

        text = (
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
            await send_clean_message(user_id, "Нет активного перерыва")
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
            user_id,
            start_time.strftime("%H:%M:%S"),
            now.strftime("%H:%M:%S"),
            minutes
        ])

        text = (
            f"🟢 Закончил перерыв\n"
            f"{message.from_user.full_name}\n"
            f"{minutes} мин"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        del break_data[user_id]

        await send_clean_message(user_id, "Перерыв завершён", reply_markup=break_keyboard)

    elif message.text == "Взять выходной":

        user_id = message.from_user.id

        if user_id in calendar_messages:
            try:
                await bot.delete_message(
                    chat_id=user_id,
                    message_id=calendar_messages[user_id]
                )
            except Exception as e:
                print("Ошибка удаления:", e)

            del calendar_messages[user_id]

        calendar_kb = generate_calendar()

        msg = await bot.send_message(
            user_id,
            "Выбери день:",
            reply_markup=calendar_kb
        )

        calendar_messages[user_id] = msg.message_id

    elif message.text == "Мои выходные":

        records = days_off_sheet.get_all_values()
        user_id_str = str(user_id)
        month = datetime.now().month

        user_days = [
            r for r in records
            if len(r) > 5 and r[3] == user_id_str and int(r[5]) == month
        ]

        if not user_days:
            await send_clean_message(user_id, "У тебя пока нет выходных")
            return

        text = "Твои выходные:\n\n"

        for r in user_days:
            text += f"{r[4]}\n"

        text += f"\nОсталось: {6 - len(user_days)}"

        await send_clean_message(user_id, text)
        
    elif message.text == "Свободные дни":

        records = days_off_sheet.get_all_values()
        now = datetime.now()
        month = now.month
        year = now.year

        text = "Свободные дни:\n\n"

        for day in range(1, 32):
            try:
                date = datetime(year, month, day)
            except:
                continue

            date_str = date.strftime("%d.%m.%Y")

            same_day = [
                r for r in records
                if len(r) > 5 and r[4] == date_str
            ]

            taken = len(same_day)

            if taken >= MAX_DAY_OFF:
                text += f"{date_str} — 🔴 занято\n"
            else:
                left = MAX_DAY_OFF - taken
                text += f"{date_str} — 🟢 {left} мест\n"

        await send_clean_message(user_id, text)

    # 💰 ЗАРПЛАТА
    elif message.text == "Моя зарплата":
        salary_waiting[user_id] = {"step": "balance"}
        await send_clean_message(user_id, "Введи баланс ($)")

    elif user_id in salary_waiting:

        step = salary_waiting[user_id]["step"]

        # 1. баланс
        if step == "balance":
            try:
                balance = float(message.text)
            except:
                await send_clean_message(user_id, "Введи число")
                return

            salary_waiting[user_id]["balance"] = balance
            salary_waiting[user_id]["step"] = "percent"

            await send_clean_message(user_id, "Введи процент (например 45)")

        # 2. процент
        elif step == "percent":
            try:
                percent = float(message.text)
            except:
                await send_clean_message(user_id, "Введи число")
                return

            salary_waiting[user_id]["percent"] = percent
            salary_waiting[user_id]["step"] = "gifts"

            await send_clean_message(user_id, "Введи сумму подарков ($)")

        # 3. подарки
        elif step == "gifts":
            try:
                gifts = float(message.text)
            except:
                await send_clean_message(user_id, "Введи число")
                return

            salary_waiting[user_id]["gifts"] = gifts
            salary_waiting[user_id]["step"] = "gifts_percent"

            await send_clean_message(user_id, "Введи процент с подарков (20-25)")

        # 4. финал
        elif step == "gifts_percent":
            try:
                gifts_percent = float(message.text)
            except:
                await send_clean_message(user_id, "Введи число")
                return

            data = salary_waiting[user_id]

            balance = data["balance"]
            percent = data["percent"]
            gifts = data["gifts"]

            # баланс
            clean_balance = balance * (percent / 100)
            cashout_balance = clean_balance * 0.04
            final_balance = clean_balance - cashout_balance

            # подарки
            clean_gifts = gifts * (gifts_percent / 100)
            cashout_gifts = clean_gifts * 0.04
            final_gifts = clean_gifts - cashout_gifts

            total = final_balance + final_gifts

            await send_clean_message(
                user_id,
                f"💰 ТВОЯ ЗАРПЛАТА:\n\n"
                f"Баланс:\n"
                f"{clean_balance:.2f} - 4% = {final_balance:.2f}\n\n"
                f"Подарки:\n"
                f"{clean_gifts:.2f} - 4% = {final_gifts:.2f}\n\n"
                f"ИТОГ:\n"
                f"{total:.2f}$",
                reply_markup=salary_keyboard
            )

            del salary_waiting[user_id]

@dp.callback_query(F.data == "ignore")
async def ignore_click(callback: CallbackQuery):
    await callback.answer("Недоступно", show_alert=False)
    
@dp.callback_query(F.data.startswith("day_"))
async def select_day(callback: CallbackQuery):

    await callback.answer()

    user_id = callback.from_user.id
    data = callback.data.split("_")

    day = int(data[1])
    month = int(data[2])
    year = datetime.now().year

    selected_date = datetime(year, month, day)

    records = days_off_sheet.get_all_values()
    user_id_str = str(user_id)

    # 🔹 проверка 6 выходных
    user_days = [
        r for r in records
        if len(r) > 5 and r[3] == user_id_str and int(r[5]) == month
    ]

    if len(user_days) >= 6:
        await callback.message.answer("❌ У тебя уже 6 выходных в этом месяце")
        return

    # ❌ проверка что уже брал этот день
    already_taken = [
        r for r in records
        if len(r) > 5 and r[3] == user_id_str and r[4] == selected_date.strftime("%d.%m.%Y")
    ]

    if already_taken:
        await callback.message.answer("❌ Ты уже взял этот день")
        return
    
    # 🔹 проверка 20%
    same_day = [
        r for r in records
        if len(r) > 5 and r[4] == selected_date.strftime("%d.%m.%Y")
    ]

    if len(same_day) >= MAX_DAY_OFF:
        await callback.message.answer("❌ На этот день уже нет мест")
        return

    # 🔹 список людей
    user_list = []

    for r in same_day:
        username = r[2]
        if username and username != "без username":
            user_list.append(f"@{username}")
        else:
            user_list.append(r[1])

    list_text = ""
    if user_list:
        list_text = "\n\nУже взяли:\n" + "\n".join(user_list)

    # 🔹 запись
    days_off_sheet.append_row([
        datetime.now().strftime("%d.%m.%Y"),
        callback.from_user.full_name,
        callback.from_user.username or "без username",
        user_id,
        selected_date.strftime("%d.%m.%Y"),
        month
    ])

    remaining = MAX_DAY_OFF - (len(same_day) + 1)

    text = (
        f"📅 Взял выходной\n"
        f"@{callback.from_user.username if callback.from_user.username else 'без username'}\n"
        f"{selected_date.strftime('%d.%m.%Y')}\n"
        f"Осталось мест: {remaining}"
        f"{list_text}"
    )

    # 🔹 отправка
    await bot.send_message(ADMIN_ID, text)
    await bot.send_message(OWNER_ID, text)

    for u in users:
        if u == user_id:
            continue
        try:
            await bot.send_message(u, text)
        except:
            pass

    await callback.message.edit_text("✅ Выходной сохранён")

    if user_id in calendar_messages:
        del calendar_messages[user_id]


@dp.message(F.text == "/users")
async def show_users(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not users:
        await message.answer("Нет пользователей")
        return

    text = "Пользователи:\n\n"

    for u in users:
        text += f"{u}\n"

    await message.answer(text)


@dp.message(F.text.startswith("/block"))
async def block_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(message.text.split()[1])
        blocked_users.add(user_id)
        await message.answer(f"Заблокирован: {user_id}")
    except:
        await message.answer("Ошибка. Пример: /block 123456789")


@dp.message(F.text.startswith("/unblock"))
async def unblock_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(message.text.split()[1])
        blocked_users.discard(user_id)
        await message.answer(f"Разблокирован: {user_id}")
    except:
        await message.answer("Ошибка. Пример: /unblock 123456789")

# ЗАПУСК
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
