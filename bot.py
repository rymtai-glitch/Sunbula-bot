import os
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from supabase import create_client, Client

# ── Config ─────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8887485175:AAFR7HoGUrV5_o8JdHD6LKlY3f7XjNn4Ym8")
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://knofisuaqxpqxplktgsw.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imtub2Zpc3VhcXhwcXhwbGt0Z3N3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODAyMDYwODgsImV4cCI6MjA5NTc4MjA4OH0.huhDNaF5FN9_YqMzasFM8DssSwPKufRxtJ2SKqb_8ME")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Employees ──────────────────────────────────────────────────────────────
EMPLOYEES = [
    "Бариста Виктория", "Бариста Дияр", "Бариста Ансаган", "Бариста Динара",
    "Повар Нурсултан", "Повар Бека", "Повар Гульнар", "Повар Айнур",
    "Повар Асанали", "Повар Сабина"
]

# ── States ─────────────────────────────────────────────────────────────────
class CheckIn(StatesGroup):
    choosing_employee = State()
    taking_photo = State()

class CheckOut(StatesGroup):
    choosing_employee = State()
    taking_photo = State()

class Report(StatesGroup):
    cash = State()
    kaspi = State()
    glovo = State()
    wolt = State()
    yandex = State()
    returns = State()
    checks_count = State()

class Invoice(StatesGroup):
    photo = State()
    store = State()
    item = State()
    quantity = State()
    price = State()

class SalaryMenu(StatesGroup):
    main = State()
    choosing_employee = State()
    amount = State()
    fine_employee = State()
    fine_amount = State()
    fine_reason = State()
    advance_employee = State()
    advance_amount = State()

# ── Keyboards ──────────────────────────────────────────────────────────────
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Накладная"), KeyboardButton(text="📊 Отчет")],
            [KeyboardButton(text="🟢 Приход"),    KeyboardButton(text="🔴 Уход")],
        ],
        resize_keyboard=True
    )

def employees_keyboard(prefix=""):
    buttons = []
    row = []
    for i, emp in enumerate(EMPLOYEES):
        row.append(InlineKeyboardButton(text=emp, callback_data=f"{prefix}:{emp}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def uid():
    import random, string
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def now_str():
    tz = timedelta(hours=5)  # Kazakhstan UTC+5
    return (datetime.utcnow() + tz).strftime("%d.%m.%Y %H:%M")

def today_str():
    tz = timedelta(hours=5)
    return (datetime.utcnow() + tz).strftime("%Y-%m-%d")

def time_str():
    tz = timedelta(hours=5)
    return (datetime.utcnow() + tz).strftime("%H:%M")

# ── /start ─────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "☕ <b>Sunbula Finance Bot</b>\n\nВыберите действие:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

# ── ПРИХОД ─────────────────────────────────────────────────────────────────
@dp.message(F.text == "🟢 Приход")
async def checkin_start(message: Message, state: FSMContext):
    await state.set_state(CheckIn.choosing_employee)
    await message.answer(
        "👤 Выберите сотрудника для прихода:",
        reply_markup=employees_keyboard("checkin")
    )

@dp.callback_query(F.data.startswith("checkin:"))
async def checkin_employee(callback: CallbackQuery, state: FSMContext):
    employee = callback.data.split(":", 1)[1]
    await state.update_data(employee=employee, time=time_str(), date=today_str())
    await state.set_state(CheckIn.taking_photo)
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        f"📸 Сделайте фото для прихода\n_(Откройте камеру и сфотографируйтесь — не отправляйте старое фото)_",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(CheckIn.taking_photo, F.photo)
async def checkin_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⏳ Загружаю фото...")

    try:
        supabase.table("shifts").insert({
            "id": uid(),
            "employee": data["employee"],
            "type": "checkin",
            "time": data["time"],
            "date": data["date"],
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        await message.answer(
            f"✅ <b>Приход зафиксирован!</b>\n\n"
            f"👤 Сотрудник: <b>{data['employee']}</b>\n"
            f"🕐 Время: {data['time']}\n"
            f"📅 Дата: {now_str().split()[0]}\n"
            f"⚠️ Фото не загружено",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

@dp.message(CheckIn.taking_photo, F.text == "❌ Отмена")
async def checkin_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard())

# ── УХОД ───────────────────────────────────────────────────────────────────
@dp.message(F.text == "🔴 Уход")
async def checkout_start(message: Message, state: FSMContext):
    await state.set_state(CheckOut.choosing_employee)
    await message.answer(
        "👤 Выберите сотрудника для ухода:",
        reply_markup=employees_keyboard("checkout")
    )

@dp.callback_query(F.data.startswith("checkout:"))
async def checkout_employee(callback: CallbackQuery, state: FSMContext):
    employee = callback.data.split(":", 1)[1]
    await state.update_data(employee=employee, time=time_str(), date=today_str())
    await state.set_state(CheckOut.taking_photo)
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        f"📸 Сделайте фото для ухода\n_(Откройте камеру и сфотографируйтесь — не отправляйте старое фото)_",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(CheckOut.taking_photo, F.photo)
async def checkout_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⏳ Обрабатываю уход...")

    try:
        # Find checkin to calculate hours
        checkin = supabase.table("shifts").select("*")\
            .eq("employee", data["employee"])\
            .eq("date", data["date"])\
            .eq("type", "checkin")\
            .order("created_at", desc=True)\
            .limit(1).execute()

        checkin_time = checkin.data[0]["time"] if checkin.data else None
        hours_worked = "0ч 0мин"
        if checkin_time:
            try:
                t1 = datetime.strptime(checkin_time, "%H:%M")
                t2 = datetime.strptime(data["time"], "%H:%M")
                diff = t2 - t1
                mins = int(diff.total_seconds() / 60)
                hours_worked = f"{mins // 60}ч {mins % 60}мин"
            except:
                pass

        supabase.table("shifts").insert({
            "id": uid(),
            "employee": data["employee"],
            "type": "checkout",
            "time": data["time"],
            "date": data["date"],
            "hours_worked": hours_worked,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        await message.answer(
            f"✅ <b>Уход зафиксирован!</b>\n\n"
            f"☕ Сотрудник: <b>{data['employee']}</b>\n"
            f"🟢 Приход: {checkin_time or '—'}\n"
            f"🔴 Уход: {data['time']}\n"
            f"🕐 Отработано: <b>{hours_worked}</b>\n"
            f"📋 Смена: —\n"
            f"⚠️ Фото не загружено",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

@dp.message(CheckOut.taking_photo, F.text == "❌ Отмена")
async def checkout_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard())

# ── ОТЧЕТ ──────────────────────────────────────────────────────────────────
@dp.message(F.text == "📊 Отчет")
async def report_start(message: Message, state: FSMContext):
    await state.set_state(Report.cash)
    await message.answer(
        "📊 <b>Дневной отчет</b>\n\nВведите сумму <b>Наличных</b> (₸):",
        reply_markup=cancel_keyboard(),
        parse_mode="HTML"
    )

@dp.message(Report.cash)
async def report_cash(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(cash=float(message.text.replace(" ", "")))
        await state.set_state(Report.kaspi)
        await message.answer("Введите сумму <b>Kaspi QR</b> (₸):", parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.kaspi)
async def report_kaspi(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(kaspi=float(message.text.replace(" ", "")))
        await state.set_state(Report.glovo)
        await message.answer("Введите сумму <b>Glovo</b> (₸):", parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.glovo)
async def report_glovo(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(glovo=float(message.text.replace(" ", "")))
        await state.set_state(Report.wolt)
        await message.answer("Введите сумму <b>Wolt</b> (₸):", parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.wolt)
async def report_wolt(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(wolt=float(message.text.replace(" ", "")))
        await state.set_state(Report.yandex)
        await message.answer("Введите сумму <b>Яндекс</b> (₸):", parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.yandex)
async def report_yandex(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(yandex=float(message.text.replace(" ", "")))
        await state.set_state(Report.returns)
        await message.answer("Введите сумму <b>возвратов</b> (₸):", parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.returns)
async def report_returns(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(returns=float(message.text.replace(" ", "")))
        await state.set_state(Report.checks_count)
        await message.answer("Введите <b>количество чеков</b>:", parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.checks_count)
async def report_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        data = await state.get_data()
        checks = int(message.text.replace(" ", ""))
        total = data["cash"] + data["kaspi"] + data["glovo"] + data["wolt"] + data["yandex"] - data["returns"]
        avg = round(total / checks) if checks > 0 else 0

        # Save to Supabase as transactions
        date = today_str()
        entries = [
            ("Cash", data["cash"]),
            ("Kaspi QR", data["kaspi"]),
            ("Glovo", data["glovo"]),
            ("Wolt", data["wolt"]),
            ("Yandex", data["yandex"]),
        ]
        for cat, amount in entries:
            if amount > 0:
                supabase.table("transactions").insert({
                    "id": uid(),
                    "type": "income",
                    "amount": amount,
                    "category": cat,
                    "description": f"Отчет за {now_str().split()[0]}",
                    "date": date,
                    "created_at": datetime.utcnow().isoformat()
                }).execute()

        # Save daily report
        supabase.table("daily_reports").upsert({
            "id": date,
            "date": date,
            "cash": data["cash"],
            "kaspi": data["kaspi"],
            "glovo": data["glovo"],
            "wolt": data["wolt"],
            "yandex": data["yandex"],
            "returns": data["returns"],
            "checks_count": checks,
            "total": total,
            "avg_check": avg,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        # Monthly stats
        month_start = today_str()[:7] + "-01"
        monthly = supabase.table("daily_reports").select("total")\
            .gte("date", month_start).execute()
        month_total = sum(r["total"] for r in monthly.data) if monthly.data else total
        days_count = len(monthly.data) if monthly.data else 1
        avg_daily = round(month_total / days_count)

        await message.answer(
            f"✅ <b>Отчет сохранен!</b>\n\n"
            f"📅 Дата: {now_str()}\n\n"
            f"💵 Наличные:   {int(data['cash']):,} ₸\n"
            f"📲 Kaspi QR:   {int(data['kaspi']):,} ₸\n"
            f"🟢 Glovo:      {int(data['glovo']):,} ₸\n"
            f"🚀 Wolt:       {int(data['wolt']):,} ₸\n"
            f"🚕 Яндекс:     {int(data['yandex']):,} ₸\n"
            f"🔄 Возвраты:   {int(data['returns']):,} ₸\n"
            f"{'—'*30}\n"
            f"💰 Общая выручка: <b>{int(total):,} ₸</b>\n"
            f"🧾 Кол-во чеков: {checks}\n"
            f"📊 Средний чек: <b>{int(avg):,} ₸</b>\n"
            f"{'—'*30}\n"
            f"📅 Месяц к сегодня: {int(month_total):,} ₸\n"
            f"📅 Ср. выручка в день: {int(avg_daily):,} ₸ ({days_count} дн.)",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

# ── НАКЛАДНАЯ ──────────────────────────────────────────────────────────────
@dp.message(F.text == "📦 Накладная")
async def invoice_start(message: Message, state: FSMContext):
    await state.set_state(Invoice.photo)
    await message.answer(
        "📸 Сфотографируйте накладную:",
        reply_markup=cancel_keyboard()
    )

@dp.message(Invoice.photo, F.photo)
async def invoice_photo(message: Message, state: FSMContext):
    await message.answer("✅ Фото получено.\n\nВведите <b>магазин</b>:", parse_mode="HTML")
    await state.set_state(Invoice.store)

@dp.message(Invoice.photo, F.text == "❌ Отмена")
async def invoice_photo_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard())

@dp.message(Invoice.store)
async def invoice_store(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    await state.update_data(store=message.text)
    await state.set_state(Invoice.item)
    await message.answer("Введите <b>товар</b>:", parse_mode="HTML")

@dp.message(Invoice.item)
async def invoice_item(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    await state.update_data(item=message.text)
    await state.set_state(Invoice.quantity)
    await message.answer("Введите <b>количество</b>:", parse_mode="HTML")

@dp.message(Invoice.quantity)
async def invoice_quantity(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    await state.update_data(quantity=message.text)
    await state.set_state(Invoice.price)
    await message.answer("Введите <b>цену</b>:", parse_mode="HTML")

@dp.message(Invoice.price)
async def invoice_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        data = await state.get_data()
        price = float(message.text.replace(" ", ""))
        date = today_str()

        supabase.table("invoices").insert({
            "id": uid(),
            "date": date,
            "store": data["store"],
            "item": data["item"],
            "quantity": data["quantity"],
            "price": price,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        supabase.table("transactions").insert({
            "id": uid(),
            "type": "expense",
            "amount": price,
            "category": "Магазин",
            "description": f"{data['store']} — {data['item']} x{data['quantity']}",
            "date": date,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        await message.answer(
            f"✅ <b>Накладная сохранена!</b>\n\n"
            f"📅 Дата: {now_str()}\n"
            f"🏪 Магазин: {data['store']}\n"
            f"📦 Товар: {data['item']}\n"
            f"🔢 Количество: {data['quantity']}\n"
            f"💰 Цена: {int(price):,} ₸",
            reply_markup=main_keyboard(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

# ── Cancel callback ─────────────────────────────────────────────────────────
@dp.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer("Отменено.", reply_markup=main_keyboard())
    await callback.answer()

# ── Run ─────────────────────────────────────────────────────────────────────
async def main():
    # Create tables if needed
    try:
        supabase.table("shifts").select("id").limit(1).execute()
        supabase.table("daily_reports").select("id").limit(1).execute()
        supabase.table("invoices").select("id").limit(1).execute()
    except:
        pass
    logger.info("Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
