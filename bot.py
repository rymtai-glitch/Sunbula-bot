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

# ── Employee config ─────────────────────────────────────────────────────────
# type: 'shift' = полная/половина смены, 'hourly' = почасовая, 'count' = только счётчик, 'fixed' = фиксированная
EMPLOYEES = {
    "Нурсултан": {"type": "shift", "full": 25000, "half": 15000},
    "Бека":       {"type": "shift", "full": 23000, "half": 15000},
    "Куралай":    {"type": "fixed", "amount": 15000},
    "Дияр":       {"type": "hourly", "rate": 1500},
    "Виктория":   {"type": "hourly", "rate": 1350},
    "Ансаган":    {"type": "count"},
    "Динара":     {"type": "count"},
}

EMPLOYEE_NAMES = list(EMPLOYEES.keys())

# ── Helpers ─────────────────────────────────────────────────────────────────
def today_str():
    tz = timedelta(hours=5)
    return (datetime.utcnow() + tz).strftime("%Y-%m-%d")

def now_str():
    tz = timedelta(hours=5)
    return (datetime.utcnow() + tz).strftime("%d.%m.%Y %H:%M")

def time_str():
    tz = timedelta(hours=5)
    return (datetime.utcnow() + tz).strftime("%H:%M")

def uid():
    import random, string
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def calc_hours(t1_str, t2_str):
    try:
        t1 = datetime.strptime(t1_str, "%H:%M")
        t2 = datetime.strptime(t2_str, "%H:%M")
        if t2 < t1:
            t2 += timedelta(hours=24)
        diff_mins = int((t2 - t1).total_seconds() / 60)
        hours = diff_mins / 60
        return hours, diff_mins
    except:
        return 0, 0

def fmt_money(n):
    return f"{int(n):,}".replace(",", " ")

# ── States ──────────────────────────────────────────────────────────────────
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

# ── Keyboards ───────────────────────────────────────────────────────────────
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Накладная"), KeyboardButton(text="📊 Отчет")],
            [KeyboardButton(text="🟢 Приход"),    KeyboardButton(text="🔴 Уход")],
        ],
        resize_keyboard=True
    )

def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )

def employees_inline(prefix):
    buttons = []
    row = []
    for name in EMPLOYEE_NAMES:
        row.append(InlineKeyboardButton(text=name, callback_data=f"{prefix}:{name}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def shift_type_keyboard(employee):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌕 Полная смена", callback_data=f"shift_full:{employee}")],
        [InlineKeyboardButton(text="🌗 Половина смены", callback_data=f"shift_half:{employee}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])

# ── /start ──────────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "☕ <b>Sunbula Finance Bot</b>\n\nВыберите действие:",
        reply_markup=main_keyboard(),
        parse_mode="HTML"
    )

# ── ПРИХОД ───────────────────────────────────────────────────────────────────
@dp.message(F.text == "🟢 Приход")
async def checkin_start(message: Message, state: FSMContext):
    await state.set_state(CheckIn.choosing_employee)
    await message.answer("👤 Выберите сотрудника:", reply_markup=employees_inline("checkin"))

@dp.callback_query(F.data.startswith("checkin:"))
async def checkin_employee(callback: CallbackQuery, state: FSMContext):
    employee = callback.data.split(":", 1)[1]
    await state.update_data(employee=employee, time=time_str(), date=today_str())
    await state.set_state(CheckIn.taking_photo)
    await callback.message.edit_reply_markup()
    await callback.message.answer(
        "📸 Сделайте фото для прихода\n_(Откройте камеру — не отправляйте старое фото)_",
        reply_markup=cancel_keyboard(), parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(CheckIn.taking_photo, F.photo)
async def checkin_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("⏳ Загружаю фото...")
    try:
        supabase.table("shifts").insert({
            "id": uid(), "employee": data["employee"],
            "type": "checkin", "time": data["time"],
            "date": data["date"], "created_at": datetime.utcnow().isoformat()
        }).execute()
        await message.answer(
            f"✅ <b>Приход зафиксирован!</b>\n\n"
            f"👤 Сотрудник: <b>{data['employee']}</b>\n"
            f"🕐 Время: {data['time']}\n"
            f"📅 Дата: {data['date']}\n"
            f"⚠️ Фото не загружено",
            reply_markup=main_keyboard(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

@dp.message(CheckIn.taking_photo, F.text == "❌ Отмена")
async def checkin_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard())

# ── УХОД ─────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🔴 Уход")
async def checkout_start(message: Message, state: FSMContext):
    await state.set_state(CheckOut.choosing_employee)
    await message.answer("👤 Выберите сотрудника:", reply_markup=employees_inline("checkout"))

@dp.callback_query(F.data.startswith("checkout:"))
async def checkout_employee(callback: CallbackQuery, state: FSMContext):
    employee = callback.data.split(":", 1)[1]
    emp_config = EMPLOYEES[employee]
    checkout_time = time_str()
    date = today_str()

    await callback.message.edit_reply_markup()

    # For shift-type employees, ask shift type instead of photo
    if emp_config["type"] == "shift":
        await state.update_data(employee=employee, time=checkout_time, date=date)
        await state.set_state(CheckOut.taking_photo)
        await callback.message.answer(
            f"👤 <b>{employee}</b>\nВыберите тип смены:",
            reply_markup=shift_type_keyboard(employee), parse_mode="HTML"
        )
        await callback.answer()
        return

    await state.update_data(employee=employee, time=checkout_time, date=date)
    await state.set_state(CheckOut.taking_photo)
    await callback.message.answer(
        "📸 Сделайте фото для ухода\n_(Откройте камеру — не отправляйте старое фото)_",
        reply_markup=cancel_keyboard(), parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("shift_full:") | F.data.startswith("shift_half:"))
async def shift_type_chosen(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split(":", 1)
    shift_type = "full" if parts[0] == "shift_full" else "half"
    employee = parts[1]
    emp_config = EMPLOYEES[employee]
    data = await state.get_data()

    salary = emp_config["full"] if shift_type == "full" else emp_config["half"]
    shift_label = "Полная смена" if shift_type == "full" else "Половина смены"

    await callback.message.edit_reply_markup()

    try:
        supabase.table("shifts").insert({
            "id": uid(), "employee": employee,
            "type": "checkout", "time": data.get("time", time_str()),
            "date": data.get("date", today_str()),
            "shift_type": shift_type, "salary": salary,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        # Save to salary_records
        supabase.table("salary_records").insert({
            "id": uid(), "employee": employee,
            "date": data.get("date", today_str()),
            "shift_type": shift_label, "hours": None,
            "salary": salary, "rate_type": "shift",
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        await callback.message.answer(
            f"✅ <b>Смена зафиксирована!</b>\n\n"
            f"👤 Сотрудник: <b>{employee}</b>\n"
            f"📋 Смена: {shift_label}\n"
            f"💰 Начислено: <b>{fmt_money(salary)} ₸</b>",
            reply_markup=main_keyboard(), parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())

    await state.clear()
    await callback.answer()

@dp.message(CheckOut.taking_photo, F.photo)
async def checkout_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    employee = data["employee"]
    emp_config = EMPLOYEES[employee]
    await message.answer("⏳ Обрабатываю уход...")

    try:
        # Get checkin time
        checkin = supabase.table("shifts").select("*")\
            .eq("employee", employee).eq("date", data["date"])\
            .eq("type", "checkin").order("created_at", desc=True)\
            .limit(1).execute()

        checkin_time = checkin.data[0]["time"] if checkin.data else None
        hours_worked_f = 0
        diff_mins = 0
        hours_label = "—"
        salary = 0
        salary_label = ""

        if checkin_time:
            hours_worked_f, diff_mins = calc_hours(checkin_time, data["time"])
            hours_label = f"{diff_mins // 60}ч {diff_mins % 60}мин"

        if emp_config["type"] == "hourly":
            salary = round(hours_worked_f * emp_config["rate"])
            salary_label = f"\n💰 Начислено: <b>{fmt_money(salary)} ₸</b> ({hours_worked_f:.1f}ч × {fmt_money(emp_config['rate'])} ₸)"
        elif emp_config["type"] == "fixed":
            salary = emp_config["amount"]
            salary_label = f"\n💰 Начислено: <b>{fmt_money(salary)} ₸</b>"
        elif emp_config["type"] == "count":
            salary_label = f"\n📊 Смена засчитана"

        supabase.table("shifts").insert({
            "id": uid(), "employee": employee,
            "type": "checkout", "time": data["time"],
            "date": data["date"], "checkin_time": checkin_time,
            "hours_worked": hours_label, "salary": salary,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        if salary > 0:
            supabase.table("salary_records").insert({
                "id": uid(), "employee": employee,
                "date": data["date"],
                "shift_type": "Полная смена",
                "hours": round(hours_worked_f, 2),
                "salary": salary, "rate_type": emp_config["type"],
                "checkin_time": checkin_time, "checkout_time": data["time"],
                "created_at": datetime.utcnow().isoformat()
            }).execute()
        elif emp_config["type"] == "count":
            supabase.table("salary_records").insert({
                "id": uid(), "employee": employee,
                "date": data["date"], "shift_type": "Смена",
                "hours": round(hours_worked_f, 2),
                "salary": 0, "rate_type": "count",
                "checkin_time": checkin_time, "checkout_time": data["time"],
                "created_at": datetime.utcnow().isoformat()
            }).execute()

        await message.answer(
            f"✅ <b>Уход зафиксирован!</b>\n\n"
            f"☕ Сотрудник: <b>{employee}</b>\n"
            f"🟢 Приход: {checkin_time or '—'}\n"
            f"🔴 Уход: {data['time']}\n"
            f"🕐 Отработано: <b>{hours_label}</b>"
            f"{salary_label}\n"
            f"⚠️ Фото не загружено",
            reply_markup=main_keyboard(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

@dp.message(CheckOut.taking_photo, F.text == "❌ Отмена")
async def checkout_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_keyboard())

# ── ОТЧЕТ ────────────────────────────────────────────────────────────────────
@dp.message(F.text == "📊 Отчет")
async def report_start(message: Message, state: FSMContext):
    await state.set_state(Report.cash)
    await message.answer(
        "📊 <b>Дневной отчет</b>\n\nВведите сумму <b>Наличных</b> (₸):",
        reply_markup=cancel_keyboard(), parse_mode="HTML"
    )

async def get_report_val(message, state, next_state, next_prompt, key):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        await state.update_data(**{key: float(message.text.replace(" ", "").replace(",", "."))})
        await state.set_state(next_state)
        await message.answer(next_prompt, parse_mode="HTML")
    except:
        await message.answer("Введите число:")

@dp.message(Report.cash)
async def r_cash(message: Message, state: FSMContext):
    await get_report_val(message, state, Report.kaspi, "Введите сумму <b>Kaspi QR</b> (₸):", "cash")

@dp.message(Report.kaspi)
async def r_kaspi(message: Message, state: FSMContext):
    await get_report_val(message, state, Report.glovo, "Введите сумму <b>Glovo</b> (₸):", "kaspi")

@dp.message(Report.glovo)
async def r_glovo(message: Message, state: FSMContext):
    await get_report_val(message, state, Report.wolt, "Введите сумму <b>Wolt</b> (₸):", "glovo")

@dp.message(Report.wolt)
async def r_wolt(message: Message, state: FSMContext):
    await get_report_val(message, state, Report.yandex, "Введите сумму <b>Яндекс</b> (₸):", "wolt")

@dp.message(Report.yandex)
async def r_yandex(message: Message, state: FSMContext):
    await get_report_val(message, state, Report.returns, "Введите сумму <b>возвратов</b> (₸):", "yandex")

@dp.message(Report.returns)
async def r_returns(message: Message, state: FSMContext):
    await get_report_val(message, state, Report.checks_count, "Введите <b>количество чеков</b>:", "returns")

@dp.message(Report.checks_count)
async def r_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_keyboard())
    try:
        data = await state.get_data()
        checks = int(message.text.replace(" ", ""))
        total = data["cash"] + data["kaspi"] + data["glovo"] + data["wolt"] + data["yandex"] - data["returns"]
        avg = round(total / checks) if checks > 0 else 0
        date = today_str()

        # Save transactions
        for cat, amount in [("Cash", data["cash"]), ("Kaspi QR", data["kaspi"]),
                             ("Glovo", data["glovo"]), ("Wolt", data["wolt"]),
                             ("Yandex", data["yandex"])]:
            if amount > 0:
                supabase.table("transactions").insert({
                    "id": uid(), "type": "income", "amount": amount,
                    "category": cat, "description": f"Отчет {date}",
                    "date": date, "created_at": datetime.utcnow().isoformat()
                }).execute()

        supabase.table("daily_reports").upsert({
            "id": date, "date": date, "cash": data["cash"],
            "kaspi": data["kaspi"], "glovo": data["glovo"],
            "wolt": data["wolt"], "yandex": data["yandex"],
            "returns": data["returns"], "checks_count": checks,
            "total": total, "avg_check": avg,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        month_start = date[:7] + "-01"
        monthly = supabase.table("daily_reports").select("total").gte("date", month_start).execute()
        month_total = sum(r["total"] for r in monthly.data) if monthly.data else total
        days_count = len(monthly.data) if monthly.data else 1

        await message.answer(
            f"✅ <b>Отчет сохранен!</b>\n\n"
            f"📅 Дата: {now_str()}\n\n"
            f"💵 Наличные:    {fmt_money(data['cash'])} ₸\n"
            f"📲 Kaspi QR:    {fmt_money(data['kaspi'])} ₸\n"
            f"🟢 Glovo:       {fmt_money(data['glovo'])} ₸\n"
            f"🚀 Wolt:        {fmt_money(data['wolt'])} ₸\n"
            f"🚕 Яндекс:      {fmt_money(data['yandex'])} ₸\n"
            f"🔄 Возвраты:    {fmt_money(data['returns'])} ₸\n"
            f"{'—'*28}\n"
            f"💰 Выручка: <b>{fmt_money(total)} ₸</b>\n"
            f"🧾 Чеков: {checks}  |  📊 Средний: <b>{fmt_money(avg)} ₸</b>\n"
            f"{'—'*28}\n"
            f"📅 Месяц: {fmt_money(month_total)} ₸\n"
            f"📅 Ср/день: {fmt_money(round(month_total/days_count))} ₸ ({days_count} дн.)",
            reply_markup=main_keyboard(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()

# ── НАКЛАДНАЯ ─────────────────────────────────────────────────────────────────
@dp.message(F.text == "📦 Накладная")
async def invoice_start(message: Message, state: FSMContext):
    await state.set_state(Invoice.photo)
    await message.answer("📸 Сфотографируйте накладную:", reply_markup=cancel_keyboard())

@dp.message(Invoice.photo, F.photo)
async def invoice_photo(message: Message, state: FSMContext):
    await message.answer("✅ Фото получено.\n\nВведите <b>магазин</b>:", parse_mode="HTML")
    await state.set_state(Invoice.store)

@dp.message(Invoice.photo, F.text == "❌ Отмена")
async def invoice_cancel(message: Message, state: FSMContext):
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
        price = float(message.text.replace(" ", "").replace(",", "."))
        date = today_str()

        supabase.table("invoices").insert({
            "id": uid(), "date": date, "store": data["store"],
            "item": data["item"], "quantity": data["quantity"],
            "price": price, "created_at": datetime.utcnow().isoformat()
        }).execute()

        supabase.table("transactions").insert({
            "id": uid(), "type": "expense", "amount": price,
            "category": "Магазин",
            "description": f"{data['store']} — {data['item']} x{data['quantity']}",
            "date": date, "created_at": datetime.utcnow().isoformat()
        }).execute()

        await message.answer(
            f"✅ <b>Накладная сохранена!</b>\n\n"
            f"📅 {now_str()}\n"
            f"🏪 Магазин: {data['store']}\n"
            f"📦 Товар: {data['item']}\n"
            f"🔢 Кол-во: {data['quantity']}\n"
            f"💰 Цена: {fmt_money(price)} ₸",
            reply_markup=main_keyboard(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=main_keyboard())
    await state.clear()


# ── /myid ─────────────────────────────────────────────────────────────────────
@dp.message(Command("myid"))
async def myid(message: Message):
    await message.answer(
        f"🆔 Ваш Telegram ID: <code>{message.from_user.id}</code>\n"
        f"👤 Имя: {message.from_user.full_name}\n\n"
        f"Отправьте этот ID администратору.",
        parse_mode="HTML"
    )

# ── Cancel ────────────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "cancel")
async def cancel_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer("Отменено.", reply_markup=main_keyboard())
    await callback.answer()

# ── Run ───────────────────────────────────────────────────────────────────────
async def main():
    logger.info("✅ Sunbula Bot started!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
