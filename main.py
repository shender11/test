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
TOKEN = ("8697726930:AAFIPp8AktdwjdwEX-G3J6xXwZxxkmenCUU")



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
users_sheet = client.open_by_key("1UtE6yC0Wz0lYFlTcdDqWu1brarxkkqRaUITHg9Ynlt8").worksheet("Users")
settings_sheet = client.open_by_key("1UtE6yC0Wz0lYFlTcdDqWu1brarxkkqRaUITHg9Ynlt8").worksheet("Settings")
active_breaks_sheet = client.open_by_key("1UtE6yC0Wz0lYFlTcdDqWu1brarxkkqRaUITHg9Ynlt8").worksheet("ActiveBreaks")


bot = Bot(token=TOKEN)
dp = Dispatcher()

def get_telegram_link(user):
    if user.username:
        return f"https://t.me/{user.username}"
    return f"tg://user?id={user.id}"


break_data = {}
waiting_time = set()
users = set()
calendar_messages = {}
last_messages = {}
blocked_users = set()
salary_waiting = {}

# загрузка пользователей из таблицы
try:
    records = users_sheet.get_all_values()
    for r in records:
        if len(r) > 1 and r[1].isdigit():
            users.add(int(r[1]))
except:
    pass



# 🔹 ГЛАВНОЕ МЕНЮ
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Перерывы")],
        [KeyboardButton(text="Выходные")],
        [KeyboardButton(text="Зарплата")],
        [KeyboardButton(text="Мой профиль")]
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
        [KeyboardButton(text="Отменить выходной")],
        [KeyboardButton(text="Мои выходные")],
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

def get_team_limit():
    try:
        records = settings_sheet.get_all_values()

        for r in records:
            if r and r[0] == "team_size":
                team_size = int(r[1])
                active = team_size - 2
                return max(1, int(active * 0.2))

    except:
        pass

    return 1

def get_setting_value(key, default_value):
    try:
        records = settings_sheet.get_all_values()
        for r in records:
            if len(r) > 1 and r[0] == key:
                return int(r[1])
    except:
        pass
    return default_value


def get_today_break_stats(user_id):
    records = sheet.get_all_values()
    today_str = datetime.now().strftime("%d.%m.%Y")

    breaks_count = 0
    total_minutes = 0

    for r in records:
        if len(r) > 6 and r[0] == today_str and r[2] == str(user_id):
            breaks_count += 1
            try:
                total_minutes += int(r[6])
            except:
                pass

    return breaks_count, total_minutes

def get_today_break_type_stats(user_id):
    records = sheet.get_all_values()
    today_str = datetime.now().strftime("%d.%m.%Y")

    breaks_15 = 0
    breaks_30 = 0

    for r in records:
        if len(r) > 7 and r[0] == today_str and r[2] == str(user_id):
            try:
                planned_minutes = int(r[7])
                if planned_minutes == 15:
                    breaks_15 += 1
                elif planned_minutes == 30:
                    breaks_30 += 1
            except:
                pass

    return breaks_15, breaks_30


def check_break_type_limit(user_id, minutes):
    breaks_15, breaks_30 = get_today_break_type_stats(user_id)

    if minutes == 15 and breaks_15 >= 4:
        return False, "❌ Ты уже использовал максимум 4 перерыва по 15 минут за сегодня"

    if minutes == 30 and breaks_30 >= 2:
        return False, "❌ Ты уже использовал максимум 2 перерыва по 30 минут за сегодня"

    return True, None



def save_active_break(user):
    try:
        records = active_breaks_sheet.get_all_values()

        for i, r in enumerate(records):
            if len(r) > 0 and r[0] == str(user.id):
                active_breaks_sheet.delete_rows(i + 1)
                break

        active_breaks_sheet.append_row([
            user.id,
            user.full_name,
            user.username or "без username",
            datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            break_data[user.id]["minutes"]
        ])
    except:
        pass


def remove_active_break(user_id):
    try:
        records = active_breaks_sheet.get_all_values()
        for i, r in enumerate(records):
            if len(r) > 0 and r[0] == str(user_id):
                active_breaks_sheet.delete_rows(i + 1)
                break
    except:
        pass


def restore_active_breaks():
    try:
        records = active_breaks_sheet.get_all_values()

        for r in records:
            if len(r) < 5:
                continue

            try:
                user_id = int(r[0])
                start_time = datetime.strptime(r[3], "%d.%m.%Y %H:%M:%S")
                minutes = int(r[4])

                break_data[user_id] = {
                    "start": start_time,
                    "minutes": minutes,
                    "active": True,
                    "name": r[1],
                    "username": r[2] if r[2] != "без username" else None
                }
            except:
                pass
    except:
        pass

restore_active_breaks()



def generate_calendar():
    now = datetime.now()
    month = now.month
    year = now.year

    records = days_off_sheet.get_all_values()
    buttons = []

    import calendar

    days_in_month = calendar.monthrange(year, month)[1]
    
    for day in range(1, days_in_month + 1):
        try:
            date = datetime(year, month, day)
        except:
            continue

        date_str = date.strftime("%d.%m.%Y")

        same_day = [
            r for r in records
            if len(r) > 1 and r[1] == date_str
        ]


        taken = len(same_day)

        if date.date() < now.date():
            text = f"⛔ {day}"
            callback = "ignore"
        else:
            limit = get_team_limit()

            if taken >= limit:
                text = f"🔴 {day}"
                callback = "ignore"
            else:
                left = limit - taken
                text = f"{day} ({left})"
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

    if minutes > 5:
        await asyncio.sleep((minutes - 5) * 60)

        if user_id in break_data and user_id not in blocked_users:
            await bot.send_message(user_id, "⏳ До конца перерыва осталось 5 минут")

        await asyncio.sleep(5 * 60)
    else:
        await asyncio.sleep(minutes * 60)

    delay_minutes = 1

    while user_id in break_data and break_data[user_id]["active"] and user_id not in blocked_users:
        admin_text = (
            f"🚨 ЗАДЕРЖИВАЕТСЯ НА ПЕРЕРЫВЕ, СРОЧНО ЗВОНИ!\n"
            f"{name}\n"
            f"@{username if username else 'без username'}\n"
            f"Опоздание: {delay_minutes} мин"
        )

        await bot.send_message(user_id, "🚨 Перерыв окончен! Вернись к работе!")
        await bot.send_message(ADMIN_ID, admin_text)
        await bot.send_message(OWNER_ID, admin_text)

        delay_minutes += 1
        await asyncio.sleep(60)




# ОСНОВНАЯ ЛОГИКА
@dp.message()
async def handle(message: Message):

    user_id = message.from_user.id

    if message.text in [
        "Перерывы", "Выходные", "Зарплата", "Мой профиль",
        "Назад",
        "Начать перерыв", "Закончить перерыв",
        "Взять выходной", "Отменить выходной",
        "Мои выходные",
        "Моя зарплата"
    ]:

        try:
            await message.delete()
        except:
            pass

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

    elif message.text == "Мой профиль":
        breaks_count, total_minutes = get_today_break_stats(user_id)
        breaks_15, breaks_30 = get_today_break_type_stats(user_id)


        records = days_off_sheet.get_all_values()
        month = datetime.now().month
        user_days = []

        for r in records:
            if len(r) > 2 and r[2] == str(user_id):
                try:
                    off_date = datetime.strptime(r[1], "%d.%m.%Y")
                    if off_date.month == month:
                        user_days.append(r)
                except:
                    pass

        remaining_days_off = 6 - len(user_days)

        text = (
            f"👤 ТВОЙ ПРОФИЛЬ\n\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username if message.from_user.username else 'без username'}\n"
            f"Осталось выходных: {remaining_days_off}\n"
            f"Перерывов сегодня: {breaks_count}\n"
            f"Из них по 15 мин: {breaks_15}/4\n"
            f"Из них по 30 мин: {breaks_30}/2\n"
            f"Минут на перерыве сегодня: {total_minutes}"
        )


        await send_clean_message(user_id, text, reply_markup=main_keyboard)
        return


    elif message.text == "Назад":
        await send_clean_message(user_id, "Главное меню", reply_markup=main_keyboard)
        return
        
    if message.text and message.text.startswith("/") and message.text != "/start":
        return
    
    if message.from_user.id in blocked_users:
        return
        
    if user_id not in users:
        users.add(user_id)
        try:
            users_sheet.append_row([
                message.from_user.full_name,
                user_id,
                message.from_user.username or "без username",
                get_telegram_link(message.from_user)
            ])
        except:
            pass

    if message.text == "Начать перерыв":
        if user_id in break_data and break_data[user_id]["active"]:
            await send_clean_message(user_id, "❗ У тебя уже есть активный перерыв", reply_markup=break_keyboard)
            return

        waiting_time.add(user_id)
        await send_clean_message(user_id, "Введи длительность перерыва: 15 или 30 минут", reply_markup=break_keyboard)



    elif user_id in waiting_time:

        if not message.text or not message.text.isdigit():
            await send_clean_message(user_id, "❗ Введи число", reply_markup=break_keyboard)
            return

        minutes = int(message.text)

        if minutes not in [15, 30]:
            await send_clean_message(user_id, "❗ Можно выбрать только 15 или 30 минут", reply_markup=break_keyboard)
            return


        allowed, error_text = check_break_type_limit(user_id, minutes)

        if not allowed:
            waiting_time.remove(user_id)
            await send_clean_message(user_id, error_text, reply_markup=break_keyboard)
            return

        waiting_time.remove(user_id)

        break_data[user_id] = {
            "start": datetime.now(),
            "minutes": minutes,
            "active": True,
            "name": message.from_user.full_name,
            "username": message.from_user.username
        }
        save_active_break(message.from_user)



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
            await send_clean_message(user_id, "Нет активного перерыва", reply_markup=break_keyboard)
            return

        data = break_data[user_id]

        now = datetime.now()
        start_time = data["start"]
        duration = now - start_time
        minutes = int(duration.total_seconds() // 60)

        sheet.append_row([
            now.strftime("%d.%m.%Y"),
            message.from_user.full_name,
            user_id,
            message.from_user.username or "без username",
            start_time.strftime("%H:%M:%S"),
            now.strftime("%H:%M:%S"),
            minutes,
            data["minutes"]
        ])




        text = (
            f"🟢 Закончил перерыв\n"
            f"{message.from_user.full_name}\n"
            f"{minutes} мин"
        )

        await bot.send_message(ADMIN_ID, text)
        await bot.send_message(OWNER_ID, text)

        break_data[user_id]["active"] = False
        remove_active_break(user_id)
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

        user_days = []
        for r in records:
            if len(r) > 2 and r[2] == user_id_str:
                try:
                    off_date = datetime.strptime(r[1], "%d.%m.%Y")
                    if off_date.month == month:
                        user_days.append(r)
                except:
                    pass

        if not user_days:
            await send_clean_message(user_id, "У тебя пока нет выходных")
            return

        text = "Твои выходные:\n\n"

        for r in user_days:
            text += f"{r[1]}\n"

        text += f"\nОсталось: {6 - len(user_days)}"

        await send_clean_message(user_id, text)

    elif message.text == "Отменить выходной":

        records = days_off_sheet.get_all_values()
        user_id_str = str(user_id)
        month = datetime.now().month

        user_days = []
        for r in records:
            if len(r) > 2 and r[2] == user_id_str:
                try:
                    off_date = datetime.strptime(r[1], "%d.%m.%Y")
                    if off_date.month == month:
                        user_days.append(r)
                except:
                    pass


        if not user_days:
            await send_clean_message(user_id, "У тебя нет выходных для отмены")
            return

        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

        buttons = []

        for r in user_days:
            date = r[1]
            buttons.append([
                InlineKeyboardButton(
                    text=date,
                    callback_data=f"cancel_{date}"
                )
            ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

        await send_clean_message(user_id, "Выбери выходной для отмены:", reply_markup=keyboard)
        
   
    # 💰 ЗАРПЛАТА
    elif message.text == "Моя зарплата":
        salary_waiting[user_id] = {"step": "balance"}
        await send_clean_message(user_id, "Введи баланс ($)")

    elif user_id in salary_waiting:

        try:
            await message.delete()
        except:
            pass

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
    user_days = []
    for r in records:
        if len(r) > 2 and r[2] == user_id_str:
            try:
                off_date = datetime.strptime(r[1], "%d.%m.%Y")
                if off_date.month == month:
                    user_days.append(r)
            except:
                pass


    if len(user_days) >= 6:
        await callback.message.answer("❌ У тебя уже 6 выходных в этом месяце")
        return

    # ❌ проверка что уже брал этот день
    already_taken = [
        r for r in records
        if len(r) > 2 and r[2] == user_id_str and r[1] == selected_date.strftime("%d.%m.%Y")
    ]

    if already_taken:
        await callback.message.answer("❌ Ты уже взял этот день")
        return
    
    # 🔹 проверка 20%
    same_day = [
        r for r in records
        if len(r) > 1 and r[1] == selected_date.strftime("%d.%m.%Y")
    ]

    if len(same_day) >= get_team_limit():
        await callback.message.answer("❌ На этот день уже нет мест")
        return

    # 🔹 список людей
    user_list = []

    for r in same_day:
        username = r[3] if len(r) > 3 else ""
        if username and username != "без username":
            user_list.append(f"@{username}")
        else:
            user_list.append(f"ID: {r[2]}")


    list_text = ""
    if user_list:
        list_text = "\n\nУже взяли:\n" + "\n".join(user_list)

    # 🔹 запись
    days_off_sheet.append_row([
        datetime.now().strftime("%d.%m.%Y"),
        selected_date.strftime("%d.%m.%Y"),
        user_id,
        callback.from_user.username or "без username"
    ])


    remaining = get_team_limit() - (len(same_day) + 1)

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

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_day(callback: CallbackQuery):

    await callback.answer()

    user_id = callback.from_user.id
    date = callback.data.replace("cancel_", "")

    records = days_off_sheet.get_all_values()

    for i, r in enumerate(records):
        if len(r) > 2 and r[2] == str(user_id) and r[1] == date:
            days_off_sheet.delete_rows(i + 1)
            break

    text = (
        f"❌ Отменил выходной\n"
        f"@{callback.from_user.username if callback.from_user.username else 'без username'}\n"
        f"{date}"
    )

    await bot.send_message(ADMIN_ID, text)
    await bot.send_message(OWNER_ID, text)

    for u in users:
        if u == user_id:
            continue
        try:
            await bot.send_message(u, text)
        except:
            pass

    await callback.message.edit_text("✅ Выходной отменён")


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

@dp.message(F.text.startswith("/delete"))
async def delete_user(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(message.text.split()[1])

        # удалить из памяти
        users.discard(user_id)
        blocked_users.discard(user_id)

        # удалить из таблицы
        records = users_sheet.get_all_values()

        for i, r in enumerate(records):
            if len(r) > 1 and r[1] == str(user_id):
                users_sheet.delete_rows(i + 1)
                break


        await message.answer(f"Удалён: {user_id}")

    except:
        await message.answer("Ошибка. Пример: /delete 123456789")

# ЗАПУСК
async def main():
    for user_id, data in break_data.items():
        asyncio.create_task(
            break_control(
                user_id,
                data["minutes"],
                data.get("name", "Без имени"),
                data.get("username")
            )
        )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
