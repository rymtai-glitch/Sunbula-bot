import os
import logging
import httpx
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ── Config ──────────────────────────────────────────────────────────────────
BOT_TOKEN     = os.getenv("BOT_TOKEN")
SUPA_URL      = os.getenv("SUPABASE_URL")
SUPA_KEY      = os.getenv("SUPABASE_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_KEY", "")
WEATHER_KEY   = os.getenv("WEATHER_KEY", "")

if not BOT_TOKEN or not SUPA_URL or not SUPA_KEY:
    raise RuntimeError("Не заданы переменные окружения: BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY. Создайте файл .env")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())
sb: Client = create_client(SUPA_URL, SUPA_KEY)

# ── Access ───────────────────────────────────────────────────────────────────
ADMIN_ID = 394382908    # @rymtayy (главный)
ADMIN_IDS = {394382908, 7990145871}  # все админы

STAFF = {
    740516816:  "Дияр",
    805285953:  "Ансаган",
    5442950426: "Динара",
    6854506621: "Бека",
    1123964256: "Виктория",
    7873998822: "Нурсултан",
}

# ── Employee config ──────────────────────────────────────────────────────────
EMP = {
    "Нурсултан": {"type": "shift",  "full": 25000, "half": 15000},
    "Бека":       {"type": "shift",  "full": 23000, "half": 15000},
    "Куралай":    {"type": "fixed",  "amount": 15000},
    "Дияр":       {"type": "hourly", "rate": 1500},
    "Виктория":   {"type": "hourly", "rate": 1350},
    "Ансаган":    {"type": "count"},
    "Динара":     {"type": "count"},
}
EMP_NAMES = list(EMP.keys())

# ── Helpers ───────────────────────────────────────────────────────────────────
def tz(): return timedelta(hours=5)
def today():   return (datetime.utcnow()+tz()).strftime("%Y-%m-%d")
def now_dt():  return (datetime.utcnow()+tz())
def now_s():   return now_dt().strftime("%d.%m.%Y %H:%M")
def time_s():  return now_dt().strftime("%H:%M")
def uid():
    import random, string
    return ''.join(random.choices(string.ascii_lowercase+string.digits, k=10))
def fmt(n):    return f"{int(n):,}".replace(",", " ")

def calc_hours(t1, t2):
    try:
        a = datetime.strptime(t1, "%H:%M")
        b = datetime.strptime(t2, "%H:%M")
        if b < a: b += timedelta(hours=24)
        mins = int((b-a).total_seconds()/60)
        return mins/60, mins
    except: return 0, 0

def calc_hours_capped(t1, t2):
    """Считает часы с ограничением 07:00-23:00 (для Дияр и Виктория).
    Если пришли раньше 07:00 — считаем с 07:00. Если ушли позже 23:00
    (включая уход после полуночи) — считаем по 23:00."""
    try:
        a = datetime.strptime(t1, "%H:%M")
        b = datetime.strptime(t2, "%H:%M")
        if b < a: b += timedelta(hours=24)
        cap_start = datetime.strptime("07:00", "%H:%M")
        cap_end   = datetime.strptime("23:00", "%H:%M")
        a = max(a, cap_start)
        b = min(b, cap_end)
        if b <= a: return 0, 0
        mins = int((b - a).total_seconds() / 60)
        return mins / 60, mins
    except: return 0, 0

CAPPED_EMPLOYEES = {"Дияр", "Виктория"}

def is_admin(uid_): return uid_ in ADMIN_IDS
def get_emp_name(uid_): return STAFF.get(uid_)

# ── Keyboards ─────────────────────────────────────────────────────────────────
def main_kb_staff():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📦 Накладная"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="🟢 Приход"),    KeyboardButton(text="🔴 Уход")],
        [KeyboardButton(text="💰 Моя зарплата")],
        [KeyboardButton(text="🛑 Стоп лист")],
    ], resize_keyboard=True)

def main_kb_admin():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📦 Накладная"), KeyboardButton(text="📊 Отчет")],
        [KeyboardButton(text="🟢 Приход"),    KeyboardButton(text="🔴 Уход")],
        [KeyboardButton(text="📈 Аналитика"), KeyboardButton(text="👥 Зарплаты")],
        [KeyboardButton(text="📋 Архив отчетов"), KeyboardButton(text="🤖 AI Контент")],
        [KeyboardButton(text="🛑 Стоп лист")],
    ], resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

def emp_inline(prefix):
    rows, row = [], []
    for n in EMP_NAMES:
        row.append(InlineKeyboardButton(text=n, callback_data=f"{prefix}:{n}"))
        if len(row)==2: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def shift_kb(emp):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌕 Полная смена", callback_data=f"sf:{emp}")],
        [InlineKeyboardButton(text="🌗 Половина смены", callback_data=f"sh:{emp}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")],
    ])

def salary_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Долг по зарплатам", callback_data="sal:debt")],
        [InlineKeyboardButton(text="⚡ Добавить штраф",    callback_data="sal:fine")],
        [InlineKeyboardButton(text="🎁 Добавить премию",   callback_data="sal:bonus")],
        [InlineKeyboardButton(text="💸 Выдать аванс",      callback_data="sal:advance")],
        [InlineKeyboardButton(text="📜 История выплат",    callback_data="sal:history")],
    ])

# ── States ────────────────────────────────────────────────────────────────────
class CI(StatesGroup):   emp=State(); photo=State()
class CO(StatesGroup):   emp=State(); photo=State()
class Rep(StatesGroup):  cash=State(); kaspi=State(); glovo=State(); wolt=State(); yandex=State(); ret=State(); chk=State(); cash_end=State()
class Inv(StatesGroup):  photo=State(); store=State(); item=State(); qty=State(); price=State()
class Sal(StatesGroup):  emp=State(); amount=State(); reason=State(); action=State()

# ── /start & /myid ────────────────────────────────────────────────────────────
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    uid_ = message.from_user.id
    if is_admin(uid_):
        await message.answer("☕ <b>Sunbula — Админ панель</b>\n\nДобро пожаловать!", reply_markup=main_kb_admin(), parse_mode="HTML")
    elif get_emp_name(uid_):
        name = get_emp_name(uid_)
        await message.answer(f"☕ Привет, <b>{name}</b>!", reply_markup=main_kb_staff(), parse_mode="HTML")
    else:
        await message.answer(
            f"👋 Привет!\n\nВаш ID: <code>{uid_}</code>\nОтправьте его администратору для получения доступа.",
            parse_mode="HTML"
        )

@dp.message(Command("myid"))
async def myid(message: Message):
    await message.answer(f"🆔 Ваш ID: <code>{message.from_user.id}</code>\nИмя: {message.from_user.full_name}", parse_mode="HTML")

# ── ПРИХОД ────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🟢 Приход")
async def ci_start(message: Message, state: FSMContext):
    uid_ = message.from_user.id
    emp_name = get_emp_name(uid_) if not is_admin(uid_) else None
    if emp_name:
        await state.update_data(employee=emp_name, time=time_s(), date=today())
        await state.set_state(CI.photo)
        await message.answer("📸 Сделайте фото:", reply_markup=cancel_kb())
    elif is_admin(uid_):
        await state.set_state(CI.emp)
        await message.answer("👤 Выберите сотрудника:", reply_markup=emp_inline("ci"))
    else:
        await message.answer("⛔ Нет доступа. Отправьте /myid администратору.")

@dp.callback_query(F.data.startswith("ci:"))
async def ci_emp(callback: CallbackQuery, state: FSMContext):
    emp = callback.data.split(":",1)[1]
    await state.update_data(employee=emp, time=time_s(), date=today())
    await state.set_state(CI.photo)
    await callback.message.edit_reply_markup()
    await callback.message.answer("📸 Сделайте фото:", reply_markup=cancel_kb())
    await callback.answer()

@dp.message(CI.photo, F.photo)
async def ci_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        sb.table("shifts").insert({
            "id": uid(), "employee": data["employee"], "type": "checkin",
            "time": data["time"], "date": data["date"],
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        await message.answer(
            f"✅ <b>Приход зафиксирован!</b>\n\n👤 <b>{data['employee']}</b>\n🕐 {data['time']}  📅 {data['date']}",
            reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff(),
            parse_mode="HTML"
        )

        # 🔔 Уведомление админу
        if not is_admin(message.from_user.id):
            await bot.send_message(
                ADMIN_ID,
                f"🟢 <b>Приход сотрудника</b>\n\n👤 <b>{data['employee']}</b>\n🕐 {data['time']}  📅 {data['date']}",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=main_kb_staff())
    await state.clear()

@dp.message(CI.photo, F.text=="❌ Отмена")
async def ci_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())

# ── УХОД ──────────────────────────────────────────────────────────────────────
@dp.message(F.text == "🔴 Уход")
async def co_start(message: Message, state: FSMContext):
    uid_ = message.from_user.id
    emp_name = get_emp_name(uid_) if not is_admin(uid_) else None
    if emp_name:
        await state.update_data(employee=emp_name, time=time_s(), date=today())
        cfg = EMP[emp_name]
        if cfg["type"] == "shift":
            await state.set_state(CO.photo)
            await message.answer("Выберите тип смены:", reply_markup=shift_kb(emp_name))
        else:
            await state.set_state(CO.photo)
            await message.answer("📸 Сделайте фото:", reply_markup=cancel_kb())
    elif is_admin(uid_):
        await state.set_state(CO.emp)
        await message.answer("👤 Выберите сотрудника:", reply_markup=emp_inline("co"))
    else:
        await message.answer("⛔ Нет доступа.")

@dp.callback_query(F.data.startswith("co:"))
async def co_emp(callback: CallbackQuery, state: FSMContext):
    emp = callback.data.split(":",1)[1]
    cfg = EMP[emp]
    await state.update_data(employee=emp, time=time_s(), date=today())
    await state.set_state(CO.photo)
    await callback.message.edit_reply_markup()
    if cfg["type"] == "shift":
        await callback.message.answer(f"👤 <b>{emp}</b> — выберите тип смены:", reply_markup=shift_kb(emp), parse_mode="HTML")
    else:
        await callback.message.answer("📸 Сделайте фото:", reply_markup=cancel_kb())
    await callback.answer()

@dp.callback_query(F.data.startswith("sf:") | F.data.startswith("sh:"))
async def shift_chosen(callback: CallbackQuery, state: FSMContext):
    full = callback.data.startswith("sf:")
    emp  = callback.data.split(":",1)[1]
    cfg  = EMP[emp]
    salary = cfg["full"] if full else cfg["half"]
    label  = "Полная смена" if full else "Половина смены"
    data   = await state.get_data()
    try:
        sb.table("shifts").insert({
            "id": uid(), "employee": emp, "type": "checkout",
            "time": data.get("time", time_s()), "date": data.get("date", today()),
            "shift_type": label, "salary": salary,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        sb.table("salary_records").insert({
            "id": uid(), "employee": emp, "date": data.get("date", today()),
            "shift_type": label, "hours": None, "salary": salary,
            "rate_type": "shift", "created_at": datetime.utcnow().isoformat()
        }).execute()

        await callback.message.edit_reply_markup()
        await callback.message.answer(
            f"✅ <b>Смена зафиксирована!</b>\n\n👤 <b>{emp}</b>\n📋 {label}\n💰 Начислено: <b>{fmt(salary)} ₸</b>",
            reply_markup=main_kb_admin() if is_admin(callback.from_user.id) else main_kb_staff(),
            parse_mode="HTML"
        )

        # 🔔 Уведомление админу
        if not is_admin(callback.from_user.id):
            await bot.send_message(
                ADMIN_ID,
                f"🔴 <b>Уход сотрудника</b>\n\n👤 <b>{emp}</b>\n📋 {label}\n🕐 {data.get('time', time_s())}  📅 {data.get('date', today())}\n💰 Начислено: <b>{fmt(salary)} ₸</b>",
                parse_mode="HTML"
            )
    except Exception as e:
        await callback.message.answer(f"❌ {e}", reply_markup=main_kb_staff())
    await state.clear()
    await callback.answer()

@dp.message(CO.photo, F.photo)
async def co_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    emp  = data["employee"]
    cfg  = EMP[emp]
    await message.answer("⏳ Обрабатываю...")
    try:
        ci = sb.table("shifts").select("*").eq("employee", emp).eq("type", "checkin").order("created_at", desc=True).limit(1).execute()
        ci_time = ci.data[0]["time"] if ci.data else None
        ci_date = ci.data[0]["date"] if ci.data else data["date"]
        if emp in CAPPED_EMPLOYEES:
            hrs, mins = calc_hours_capped(ci_time, data["time"]) if ci_time else (0, 0)
        else:
            hrs, mins = calc_hours(ci_time, data["time"]) if ci_time else (0, 0)
        hlabel = f"{mins//60}ч {mins%60}мин"
        salary = 0; slabel = ""
        if cfg["type"] == "hourly":
            salary = round(hrs * cfg["rate"])
            slabel = f"\n💰 <b>{fmt(salary)} ₸</b>  ({hrs:.1f}ч × {fmt(cfg['rate'])} ₸/ч)"
        elif cfg["type"] == "fixed":
            salary = cfg["amount"]
            slabel = f"\n💰 <b>{fmt(salary)} ₸</b>"
        elif cfg["type"] == "count":
            slabel = "\n📊 Смена засчитана"

        sb.table("shifts").insert({
            "id": uid(), "employee": emp, "type": "checkout",
            "time": data["time"], "date": ci_date,
            "checkin_time": ci_time, "hours_worked": hlabel,
            "salary": salary, "created_at": datetime.utcnow().isoformat()
        }).execute()

        if salary > 0 or cfg["type"] == "count":
            sb.table("salary_records").insert({
                "id": uid(), "employee": emp, "date": ci_date,
                "shift_type": "Смена", "hours": round(hrs, 2),
                "salary": salary, "rate_type": cfg["type"],
                "checkin_time": ci_time, "checkout_time": data["time"],
                "created_at": datetime.utcnow().isoformat()
            }).execute()

        await message.answer(
            f"✅ <b>Уход зафиксирован!</b>\n\n👤 <b>{emp}</b>\n🟢 {ci_time or '—'} → 🔴 {data['time']}\n🕐 {hlabel}{slabel}",
            reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff(),
            parse_mode="HTML"
        )

        # 🔔 Уведомление админу
        if not is_admin(message.from_user.id):
            await bot.send_message(
                ADMIN_ID,
                f"🔴 <b>Уход сотрудника</b>\n\n👤 <b>{emp}</b>\n🟢 {ci_time or '—'} → 🔴 {data['time']}\n🕐 {hlabel}{slabel}",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=main_kb_staff())
    await state.clear()

@dp.message(CO.photo, F.text=="❌ Отмена")
async def co_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())

# ── ОТЧЕТ ─────────────────────────────────────────────────────────────────────
def parse_num(text):
    if not text: return None
    cleaned = text.replace(" ", "").replace(",", ".").replace("₸", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None

def back_kb(uid_):
    return main_kb_admin() if is_admin(uid_) else main_kb_staff()

@dp.message(F.text == "📊 Отчет")
async def rep_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Rep.cash)
    await message.answer("📊 <b>Дневной отчет</b>\n\n💵 Введите сумму <b>Наличных</b> (₸):", reply_markup=cancel_kb(), parse_mode="HTML")

@dp.message(Rep.cash)
async def rep_cash(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число (например: 50000):")
    await state.update_data(cash=n)
    await state.set_state(Rep.kaspi)
    await message.answer("📲 Введите сумму <b>Kaspi QR</b> (₸):", parse_mode="HTML")

@dp.message(Rep.kaspi)
async def rep_kaspi(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число:")
    await state.update_data(kaspi=n)
    await state.set_state(Rep.glovo)
    await message.answer("🟢 Введите сумму <b>Glovo</b> (₸):", parse_mode="HTML")

@dp.message(Rep.glovo)
async def rep_glovo(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число:")
    await state.update_data(glovo=n)
    await state.set_state(Rep.wolt)
    await message.answer("🚀 Введите сумму <b>Wolt</b> (₸):", parse_mode="HTML")

@dp.message(Rep.wolt)
async def rep_wolt(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число:")
    await state.update_data(wolt=n)
    await state.set_state(Rep.yandex)
    await message.answer("🚕 Введите сумму <b>Яндекс</b> (₸):", parse_mode="HTML")

@dp.message(Rep.yandex)
async def rep_yandex(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число:")
    await state.update_data(yandex=n)
    await state.set_state(Rep.ret)
    await message.answer("🔄 Введите сумму <b>возвратов</b> (₸):", parse_mode="HTML")

@dp.message(Rep.ret)
async def rep_ret(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число:")
    await state.update_data(ret=n)
    await state.set_state(Rep.chk)
    await message.answer("🧾 Введите <b>количество чеков</b>:", parse_mode="HTML")

@dp.message(Rep.chk)
async def rep_chk(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    try:
        chk = int(message.text.replace(" ", ""))
        await state.update_data(chk=chk)
        await state.set_state(Rep.cash_end)
        await message.answer("💵 Введите <b>остаток наличных на конец дня</b> (₸):", parse_mode="HTML")
    except:
        await message.answer("⚠️ Введите целое число:")

@dp.message(Rep.cash_end)
async def rep_finish(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=back_kb(message.from_user.id))
    n = parse_num(message.text)
    if n is None:
        return await message.answer("⚠️ Введите число (например: 15000):")

    try:
        d = await state.get_data()
        chk = d["chk"]
        cash_end = n
        total = d["cash"] + d["kaspi"] + d["glovo"] + d["wolt"] + d["yandex"] - d["ret"]
        avg = round(total / chk) if chk > 0 else 0
        dt = today()
        sender_name = get_emp_name(message.from_user.id) or "Админ"

        for cat, amt in [("Cash", d["cash"]), ("Kaspi QR", d["kaspi"]), ("Glovo", d["glovo"]),
                         ("Wolt", d["wolt"]), ("Yandex", d["yandex"])]:
            if amt > 0:
                sb.table("transactions").insert({
                    "id": uid(), "type": "income", "amount": amt,
                    "category": cat, "description": f"Отчет {dt}",
                    "date": dt, "created_at": datetime.utcnow().isoformat()
                }).execute()

        sb.table("daily_reports").upsert({
            "id": dt, "date": dt,
            "cash": d["cash"], "kaspi": d["kaspi"], "glovo": d["glovo"],
            "wolt": d["wolt"], "yandex": d["yandex"],
            "returns": d["ret"], "checks_count": chk,
            "total": total, "avg_check": avg,
            "cash_end": cash_end,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        yesterday = (now_dt() - timedelta(days=1)).strftime("%Y-%m-%d")
        yest = sb.table("daily_reports").select("*").eq("date", yesterday).execute()
        y = yest.data[0] if yest.data else None

        ms = dt[:7] + "-01"
        mo = sb.table("daily_reports").select("total").gte("date", ms).execute()
        mt = sum(r["total"] for r in mo.data) if mo.data else total
        dc = len(mo.data) or 1

        cats = [("💵 Наличные", d["cash"]), ("📲 Kaspi QR", d["kaspi"]),
                ("🟢 Glovo", d["glovo"]), ("🚀 Wolt", d["wolt"]), ("🚕 Яндекс", d["yandex"])]
        gross = sum(a for _, a in cats)
        cat_lines = ""
        for name, amt in cats:
            if amt > 0:
                pct = round(amt / gross * 100) if gross > 0 else 0
                cat_lines += f"{name}:  <b>{fmt(amt)} ₸</b>  ({pct}%)\n"

        cmp_block = ""
        if y:
            y_total = y.get("total", 0)
            diff = total - y_total
            pct = round(diff / y_total * 100) if y_total else 0
            sign = "+" if diff >= 0 else ""
            arrow = "📈" if diff >= 0 else "📉"
            cmp_block = (
                f"\n{'—'*26}\n"
                f"<b>Сравнение со вчера ({yesterday}):</b>\n"
                f"Вчера: {fmt(y_total)} ₸\n"
                f"Сегодня: {fmt(total)} ₸\n"
                f"{arrow} <b>{sign}{fmt(diff)} ₸  ({sign}{pct}%)</b>\n"
            )
            y_cats = [("💵 Наличные", "cash"), ("📲 Kaspi QR", "kaspi"),
                      ("🟢 Glovo", "glovo"), ("🚀 Wolt", "wolt"), ("🚕 Яндекс", "yandex")]
            today_vals = {"cash": d["cash"], "kaspi": d["kaspi"], "glovo": d["glovo"],
                          "wolt": d["wolt"], "yandex": d["yandex"]}
            for name, key in y_cats:
                tv = today_vals[key]; yv = y.get(key, 0) or 0
                if tv > 0 or yv > 0:
                    dd = tv - yv
                    dp2 = round(dd / yv * 100) if yv else 0
                    sg = "+" if dd >= 0 else ""
                    ar = "↑" if dd >= 0 else "↓"
                    cmp_block += f"  {name}: {ar} {sg}{fmt(dd)} ₸ ({sg}{dp2}%)\n"

        report_text = (
            f"✅ <b>Отчет сохранен!</b>\n\n"
            f"📅 Дата: {dt}  🕐 {time_s()}\n\n"
            f"<b>Выручка по каналам:</b>\n"
            f"{cat_lines}"
            f"🔄 Возвраты:  {fmt(d['ret'])} ₸\n"
            f"{'—'*26}\n"
            f"💰 Общая выручка: <b>{fmt(total)} ₸</b>\n"
            f"🧾 Чеков: {chk}  |  📊 Средний чек: <b>{fmt(avg)} ₸</b>\n"
            f"💵 Остаток наличных: <b>{fmt(cash_end)} ₸</b>\n"
            f"{cmp_block}"
            f"{'—'*26}\n"
            f"📅 Месяц: {fmt(mt)} ₸  |  Ср/день: {fmt(round(mt / dc))} ₸"
        )

        await message.answer(
            report_text,
            reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff(),
            parse_mode="HTML"
        )

        # 🔔 Уведомление админу
        if not is_admin(message.from_user.id):
            await bot.send_message(
                ADMIN_ID,
                f"📊 <b>Новый отчёт от {sender_name}!</b>\n\n"
                f"📅 {dt}  🕐 {time_s()}\n"
                f"💰 Выручка: <b>{fmt(total)} ₸</b>\n"
                f"🧾 Чеков: {chk}  |  Средний: <b>{fmt(avg)} ₸</b>\n"
                f"💵 Остаток наличных: <b>{fmt(cash_end)} ₸</b>",
                parse_mode="HTML"
            )

    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=main_kb_staff())
    await state.clear()

# ── НАКЛАДНАЯ ──────────────────────────────────────────────────────────────────
@dp.message(F.text == "📦 Накладная")
async def inv_start(message: Message, state: FSMContext):
    await state.set_state(Inv.photo)
    await message.answer("📸 Сфотографируйте накладную:", reply_markup=cancel_kb())

@dp.message(Inv.photo, F.photo)
async def inv_photo(message: Message, state: FSMContext):
    await message.answer("✅ Фото получено.\n\n🏪 Введите <b>магазин</b>:", parse_mode="HTML")
    await state.set_state(Inv.store)

@dp.message(Inv.photo, F.text=="❌ Отмена")
async def inv_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())

@dp.message(Inv.store)
async def inv_store(message: Message, state: FSMContext):
    if message.text=="❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())
    await state.update_data(store=message.text)
    await state.set_state(Inv.item)
    await message.answer("📦 Введите <b>товар</b>:", parse_mode="HTML")

@dp.message(Inv.item)
async def inv_item(message: Message, state: FSMContext):
    if message.text=="❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())
    await state.update_data(item=message.text)
    await state.set_state(Inv.qty)
    await message.answer("🔢 Введите <b>количество</b>:", parse_mode="HTML")

@dp.message(Inv.qty)
async def inv_qty(message: Message, state: FSMContext):
    if message.text=="❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())
    await state.update_data(qty=message.text)
    await state.set_state(Inv.price)
    await message.answer("💰 Введите <b>цену</b>:", parse_mode="HTML")

@dp.message(Inv.price)
async def inv_price(message: Message, state: FSMContext):
    if message.text=="❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff())
    try:
        d = await state.get_data()
        price = float(message.text.replace(" ","").replace(",","."))
        dt = today()
        sb.table("invoices").insert({
            "id": uid(), "date": dt, "store": d["store"], "item": d["item"],
            "quantity": d["qty"], "price": price,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        sb.table("transactions").insert({
            "id": uid(), "type": "expense", "amount": price, "category": "Магазин",
            "description": f"{d['store']} — {d['item']} x{d['qty']}",
            "date": dt, "created_at": datetime.utcnow().isoformat()
        }).execute()
        await message.answer(
            f"✅ <b>Накладная сохранена!</b>\n\n📅 {now_s()}\n🏪 {d['store']}\n📦 {d['item']}  x{d['qty']}\n💰 {fmt(price)} ₸",
            reply_markup=main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff(),
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=main_kb_staff())
    await state.clear()

# ── АНАЛИТИКА (только админ) ───────────────────────────────────────────────────
@dp.message(F.text == "📈 Аналитика")
async def analytics(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    try:
        dt = today(); ms = dt[:7]+"-01"
        td = sb.table("daily_reports").select("*").eq("date", dt).execute()
        mo = sb.table("daily_reports").select("*").gte("date", ms).execute()
        t_total = td.data[0]["total"] if td.data else 0
        t_chk   = td.data[0]["checks_count"] if td.data else 0
        t_avg   = td.data[0]["avg_check"] if td.data else 0
        m_total = sum(r["total"] for r in mo.data) if mo.data else 0
        m_days  = len(mo.data) or 1
        await message.answer(
            f"📈 <b>Аналитика Sunbula</b>\n\n"
            f"<b>Сегодня ({dt}):</b>\n"
            f"💰 Выручка: <b>{fmt(t_total)} ₸</b>\n"
            f"🧾 Чеков: {t_chk}  |  📊 Средний: {fmt(t_avg)} ₸\n\n"
            f"<b>Месяц к сегодня:</b>\n"
            f"💰 Итого: <b>{fmt(m_total)} ₸</b>\n"
            f"📅 Ср/день: {fmt(round(m_total/m_days))} ₸  ({m_days} дн.)",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ {e}")

# ── АРХИВ ОТЧЕТОВ (только админ) ───────────────────────────────────────────────
@dp.message(F.text == "📋 Архив отчетов")
async def archive(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    try:
        rows = sb.table("daily_reports").select("*").order("date", desc=True).limit(10).execute()
        if not rows.data:
            return await message.answer("Отчетов пока нет.")
        text = "📋 <b>Последние 10 отчетов:</b>\n\n"
        for r in rows.data:
            cash_end_val = r.get("cash_end")
            cash_end_str = f"  💵 Остаток: {fmt(cash_end_val)} ₸" if cash_end_val is not None else ""
            text += f"📅 <b>{r['date']}</b>  💰 {fmt(r['total'])} ₸  🧾 {r['checks_count']} чеков{cash_end_str}\n"
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ {e}")

# ── ЗАРПЛАТЫ (только админ) ────────────────────────────────────────────────────
@dp.message(F.text == "👥 Зарплаты")
async def salaries(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await message.answer("👥 <b>Управление зарплатами</b>", reply_markup=salary_menu_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "sal:debt")
async def sal_debt(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа.", show_alert=True)
    try:
        ms = today()[:7]+"-01"
        rows = sb.table("salary_records").select("*").gte("date", ms).execute()
        debts = {}
        for r in (rows.data or []):
            emp = r["employee"]
            if emp not in debts: debts[emp] = {"earned": 0, "paid": 0, "fines": 0, "bonuses": 0}
            rt = r.get("rate_type", "")
            if rt in ("shift","hourly","fixed","count"): debts[emp]["earned"] += r.get("salary", 0) or 0
            elif rt == "payment": debts[emp]["paid"]    += r.get("salary", 0) or 0
            elif rt == "fine":    debts[emp]["fines"]   += r.get("salary", 0) or 0
            elif rt == "bonus":   debts[emp]["bonuses"] += r.get("salary", 0) or 0
        if not debts:
            await callback.message.answer("За этот месяц данных нет.")
            await callback.answer(); return
        text = f"💰 <b>Долг по зарплатам — {today()[:7]}</b>\n\n"
        total_debt = 0
        for emp, d in debts.items():
            debt = d["earned"] + d["bonuses"] - d["fines"] - d["paid"]
            total_debt += debt
            text += f"👤 <b>{emp}</b>\n  Начислено: {fmt(d['earned'])} ₸"
            if d["bonuses"]: text += f"  +{fmt(d['bonuses'])} 🎁"
            if d["fines"]:   text += f"  -{fmt(d['fines'])} ⚡"
            if d["paid"]:    text += f"  Выплачено: {fmt(d['paid'])} ₸"
            text += f"\n  <b>К выплате: {fmt(debt)} ₸</b>\n\n"
        text += f"{'—'*26}\n💼 Итого к выплате: <b>{fmt(total_debt)} ₸</b>"
        await callback.message.answer(text, parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
    await callback.answer()

@dp.callback_query(F.data.in_({"sal:fine","sal:bonus","sal:advance"}))
async def sal_action(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа.", show_alert=True)
    action_map = {"sal:fine": "fine", "sal:bonus": "bonus", "sal:advance": "advance"}
    action = action_map[callback.data]
    labels = {"fine": "⚡ Штраф", "bonus": "🎁 Премия", "advance": "💸 Аванс"}
    await state.update_data(sal_action=action)
    await state.set_state(Sal.emp)
    await callback.message.answer(f"{labels[action]} — выберите сотрудника:", reply_markup=emp_inline("sal_emp"))
    await callback.answer()

@dp.callback_query(F.data.startswith("sal_emp:"))
async def sal_emp_chosen(callback: CallbackQuery, state: FSMContext):
    emp = callback.data.split(":", 1)[1]
    await state.update_data(sal_emp=emp)
    await state.set_state(Sal.amount)
    await callback.message.edit_reply_markup()
    await callback.message.answer(f"👤 <b>{emp}</b>\nВведите сумму (₸):", reply_markup=cancel_kb(), parse_mode="HTML")
    await callback.answer()

@dp.message(Sal.amount)
async def sal_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_kb_admin())
    try:
        amount = float(message.text.replace(" ", "").replace(",", "."))
        await state.update_data(sal_amount=amount)
        await state.set_state(Sal.reason)
        await message.answer("📝 Введите причину (или напишите «-» если без причины):")
    except:
        await message.answer("Введите число:")

@dp.message(Sal.reason)
async def sal_reason(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        return await message.answer("Отменено.", reply_markup=main_kb_admin())
    d = await state.get_data()
    action = d["sal_action"]
    emp    = d["sal_emp"]
    amount = d["sal_amount"]
    reason = message.text if message.text != "-" else ""
    labels = {"fine": "Штраф ⚡", "bonus": "Премия 🎁", "advance": "Аванс 💸"}
    try:
        sb.table("salary_records").insert({
            "id": uid(), "employee": emp, "date": today(),
            "shift_type": labels[action], "hours": None,
            "salary": amount, "rate_type": action,
            "checkin_time": reason or None,
            "created_at": datetime.utcnow().isoformat()
        }).execute()
        await message.answer(
            f"✅ <b>{labels[action]} сохранён!</b>\n\n"
            f"👤 {emp}\n💰 {fmt(amount)} ₸"
            + (f"\n📝 {reason}" if reason else ""),
            reply_markup=main_kb_admin(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ {e}", reply_markup=main_kb_admin())
    await state.clear()

@dp.callback_query(F.data == "sal:history")
async def sal_history(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Нет доступа.", show_alert=True)
    try:
        rows = sb.table("salary_records").select("*").order("created_at", desc=True).limit(20).execute()
        if not rows.data:
            await callback.message.answer("История пуста.")
            await callback.answer(); return
        text = "📜 <b>История выплат (последние 20):</b>\n\n"
        for r in rows.data:
            text += f"📅 {r['date']}  👤 {r['employee']}  {r['shift_type']}  💰 {fmt(r.get('salary', 0))} ₸\n"
        await callback.message.answer(text, parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
    await callback.answer()

# ── МОЯ ЗАРПЛАТА (для сотрудников) ────────────────────────────────────────────
@dp.message(F.text == "💰 Моя зарплата")
async def my_salary(message: Message):
    uid_ = message.from_user.id
    emp = get_emp_name(uid_) if not is_admin(uid_) else None
    if not emp:
        return await message.answer("⛔ Нет доступа.")
    try:
        ms = today()[:7]+"-01"
        rows = sb.table("salary_records").select("*").eq("employee", emp).gte("date", ms).execute()
        earned = 0; paid = 0; fines = 0; bonuses = 0; shifts = 0
        for r in (rows.data or []):
            rt = r.get("rate_type", "")
            if rt in ("shift","hourly","fixed"):
                earned += r.get("salary", 0) or 0
                shifts += 1
            elif rt == "count":
                shifts += 1
            elif rt == "payment": paid    += r.get("salary", 0) or 0
            elif rt == "fine":    fines   += r.get("salary", 0) or 0
            elif rt == "bonus":   bonuses += r.get("salary", 0) or 0
        debt = earned + bonuses - fines - paid
        text = (
            f"💰 <b>Моя зарплата — {today()[:7]}</b>\n\n"
            f"👤 {emp}\n"
            f"📋 Смен: {shifts}\n"
            f"✅ Начислено: <b>{fmt(earned)} ₸</b>\n"
        )
        if bonuses: text += f"🎁 Премии: +{fmt(bonuses)} ₸\n"
        if fines:   text += f"⚡ Штрафы: -{fmt(fines)} ₸\n"
        if paid:    text += f"💸 Выплачено: {fmt(paid)} ₸\n"
        text += f"{'—'*24}\n<b>К получению: {fmt(debt)} ₸</b>"
        await message.answer(text, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ {e}")

# ── AI КОНТЕНТ (по кнопке) ────────────────────────────────────────────────────
@dp.message(F.text == "🤖 AI Контент")
async def ai_content(message: Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await message.answer("⏳ Генерирую контент, подожди 10-15 секунд...")
    weather = await get_weather()
    dt = today()
    rows = sb.table("daily_reports").select("*").eq("date", dt).execute()
    if not rows.data:
        yesterday = (now_dt() - timedelta(days=1)).strftime("%Y-%m-%d")
        rows = sb.table("daily_reports").select("*").eq("date", yesterday).execute()
    report = rows.data[0] if rows.data else {}
    stories = await generate_stories(weather, report)
    sep = "—" * 26
    text = (
        "🤖 <b>AI Контент на сегодня</b>\n\n"
        + "🌤 <b>Погода:</b> " + weather + "\n"
        + sep + "\n\n"
        + stories
    )
    await message.answer(text, parse_mode="HTML")

# ── СТОП ЛИСТ ─────────────────────────────────────────────────────────────────
MENU_CATS = [
    ("breakfast", "🍳 Завтраки",          [(1,"Английский завтрак"),(2,"Скрэмбл с семгой"),(3,"Вафли с семгой"),(4,"Сытный завтрак"),(5,"Шакшука")]),
    ("porridge",  "🥣 Каши",              [(6,"Овсяная с вишней"),(7,"Рисовая с ягодами")]),
    ("sweet",     "🧇 Сладкие завтраки",  [(8,"Вафли с мороженым"),(9,"Панкейки"),(10,"Сырники")]),
    ("salads",    "🥗 Салаты",            [(11,"Цезарь с цыпленком"),(12,"Свежий салат"),(13,"Зелёный с семгой")]),
    ("bowls",     "🍲 Боулы",             [(14,"Боул с грудкой"),(15,"Боул с семгой")]),
    ("snacks",    "🥪 Перекусы",          [(16,"Сэндвич с индейкой"),(17,"Сэндвич с семгой"),(18,"Тост с индейкой")]),
    ("main",      "🍽 Горячее",           [(19,"Шницель"),(20,"Говяжьи рёбрышки"),(21,"Курица в сливочном"),(22,"Судак"),(23,"Имбирный цыплёнок"),(24,"Томлёное мясо"),(25,"Куриные котлеты")]),
    ("pasta",     "🍝 Паста",             [(26,"Арабьята"),(27,"Феттучини с курицей")]),
    ("pizza",     "🍕 Пиццы",             [(76,"Сырная пицца"),(28,"Пепперони"),(29,"Грибная с трюфелем"),(30,"Лосось Крем Чиз"),(31,"Терияки Чикен")]),
    ("soups",     "🍜 Супы",              [(32,"Рамен с индейкой"),(33,"Куриная лапша"),(34,"Чечевичный крем-суп"),(35,"Финский суп"),(36,"Грибной крем-суп")]),
    ("coffee",    "☕ Кофе",              [(37,"Эспрессо"),(38,"Американо"),(39,"Латте"),(40,"Капучино"),(41,"Флэт-Уайт"),(42,"Раф"),(43,"Матча-латте"),(44,"Какао"),(45,"Горячий шоколад"),(46,"Эспрессо-тоник"),(47,"Мокко")]),
    ("filter",    "🫗 Фильтр кофе",       [(48,"Батч-брю"),(49,"Колд-брю"),(50,"Колд-брю малина"),(51,"V-60 / Origami")]),
    ("signature", "🍵 Авторские напитки", [(52,"Нитро-классик"),(53,"Нитро-апельсин"),(55,"Айс-латте Крем-брюлле"),(57,"Матча-манго"),(58,"Матча с малиной"),(60,"Матча бамбл"),(61,"Кофе бамбл"),(62,"Матча-банан")]),
    ("tea",       "🫖 Авторские чаи",     [(63,"Чёрный чай"),(64,"Зелёный чай"),(65,"Жасмин-цитрус"),(66,"Дары Иссык-Куля"),(67,"Чабрец-малина"),(68,"Персик-лайм"),(69,"Облепиха-апельсин"),(70,"Тары-чай"),(71,"Груша-улун")]),
    ("lemonade",  "🍋 Лимонады",          [(72,"Персик-Ваниль"),(73,"Малина-маракуйя"),(74,"Экзотик"),(75,"Груша-ананас")]),
]
CATS_BY_ID = {c[0]: c for c in MENU_CATS}

def sl_get_stopped() -> set:
    rows = sb.table("menu_stop_list").select("menu_id").execute()
    return {int(r["menu_id"]) for r in (rows.data or [])}

def sl_cats_kb() -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(MENU_CATS), 2):
        row = [InlineKeyboardButton(text=MENU_CATS[i][1], callback_data=f"sl_c:{MENU_CATS[i][0]}")]
        if i + 1 < len(MENU_CATS):
            row.append(InlineKeyboardButton(text=MENU_CATS[i+1][1], callback_data=f"sl_c:{MENU_CATS[i+1][0]}"))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def sl_items_kb(cat_id: str, stopped: set) -> InlineKeyboardMarkup:
    cat = CATS_BY_ID.get(cat_id)
    if not cat: return InlineKeyboardMarkup(inline_keyboard=[])
    rows = []
    for item_id, item_name in cat[2]:
        icon = "❌" if item_id in stopped else "✅"
        rows.append([InlineKeyboardButton(text=f"{icon} {item_name}", callback_data=f"sl_t:{item_id}:{cat_id}")])
    rows.append([InlineKeyboardButton(text="← Назад к категориям", callback_data="sl_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@dp.message(F.text == "🛑 Стоп лист")
async def sl_start(message: Message):
    if not is_admin(message.from_user.id) and get_emp_name(message.from_user.id) is None:
        return await message.answer("⛔ Нет доступа.")
    try:
        stopped = sl_get_stopped()
        count = len(stopped)
        await message.answer(
            f"🛑 <b>Стоп лист</b>\n\nСейчас в стопе: <b>{count}</b> позиций\n\nВыберите категорию:",
            reply_markup=sl_cats_kb(), parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ {e}")

@dp.callback_query(F.data.startswith("sl_c:"))
async def sl_cat(callback: CallbackQuery):
    cat_id = callback.data[5:]
    cat = CATS_BY_ID.get(cat_id)
    if not cat:
        await callback.answer("Категория не найдена", show_alert=True)
        return
    try:
        stopped = sl_get_stopped()
        stopped_in_cat = sum(1 for item_id, _ in cat[2] if item_id in stopped)
        note = f"\n\n🛑 В стопе: {stopped_in_cat} из {len(cat[2])}" if stopped_in_cat else ""
        await callback.message.edit_text(
            f"{cat[1]}\n\n✅ в наличии  ❌ нет в наличии\nНажмите на блюдо чтобы изменить статус:{note}",
            reply_markup=sl_items_kb(cat_id, stopped)
        )
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
    await callback.answer()

@dp.callback_query(F.data.startswith("sl_t:"))
async def sl_toggle(callback: CallbackQuery):
    parts = callback.data.split(":")
    item_id = int(parts[1])
    cat_id  = parts[2]
    cat = CATS_BY_ID.get(cat_id)
    item_name = next((n for i, n in cat[2] if i == item_id), f"#{item_id}") if cat else f"#{item_id}"
    try:
        stopped = sl_get_stopped()
        if item_id in stopped:
            sb.table("menu_stop_list").delete().eq("menu_id", item_id).execute()
            stopped.discard(item_id)
            action_text = f"✅ <b>{item_name}</b> — убрано из стоп-листа"
        else:
            sb.table("menu_stop_list").insert({"menu_id": item_id}).execute()
            stopped.add(item_id)
            action_text = f"❌ <b>{item_name}</b> — добавлено в стоп-лист"

        stopped_in_cat = sum(1 for i, _ in cat[2] if i in stopped) if cat else 0
        note = f"\n\n🛑 В стопе: {stopped_in_cat} из {len(cat[2])}" if stopped_in_cat else ""
        await callback.message.edit_text(
            f"{cat[1] if cat else cat_id}\n\n✅ в наличии  ❌ нет в наличии\nНажмите на блюдо чтобы изменить статус:{note}\n\n{action_text}",
            reply_markup=sl_items_kb(cat_id, stopped), parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
    await callback.answer()

@dp.callback_query(F.data == "sl_back")
async def sl_back(callback: CallbackQuery):
    try:
        stopped = sl_get_stopped()
        count = len(stopped)
        await callback.message.edit_text(
            f"🛑 <b>Стоп лист</b>\n\nСейчас в стопе: <b>{count}</b> позиций\n\nВыберите категорию:",
            reply_markup=sl_cats_kb(), parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
    await callback.answer()

# ── Universal cancel handler ───────────────────────────────────────────────────
@dp.message(F.text == "❌ Отмена")
async def universal_cancel(message: Message, state: FSMContext):
    await state.clear()
    kb = main_kb_admin() if is_admin(message.from_user.id) else main_kb_staff()
    await message.answer("Отменено.", reply_markup=kb)

# ── Cancel callback ────────────────────────────────────────────────────────────
@dp.callback_query(F.data == "cancel")
async def cancel_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_reply_markup()
    await callback.message.answer("Отменено.", reply_markup=main_kb_admin() if is_admin(callback.from_user.id) else main_kb_staff())
    await callback.answer()

# ── ПОГОДА ────────────────────────────────────────────────────────────────────
async def get_weather():
    if not WEATHER_KEY:
        return "🌤 Погода недоступна (нет API ключа)"
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q=Astana,KZ&appid={WEATHER_KEY}&units=metric&lang=ru"
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=10)
            d = r.json()
        temp     = round(d["main"]["temp"])
        feels    = round(d["main"]["feels_like"])
        desc     = d["weather"][0]["description"].capitalize()
        humidity = d["main"]["humidity"]
        return f"🌡 {temp}°C (ощущается {feels}°C), {desc}, влажность {humidity}%"
    except Exception as e:
        return f"🌤 Погода недоступна ({e})"

# ── AI STORIES ─────────────────────────────────────────────────────────────────
async def generate_stories(weather: str, report: dict) -> str:
    if not ANTHROPIC_KEY:
        return "🤖 AI недоступен (нет API ключа)"
    try:
        total    = report.get("total", 0)
        checks   = report.get("checks_count", 0)
        avg      = report.get("avg_check", 0)
        cash_end = report.get("cash_end", 0)
        weekday  = now_dt().strftime("%A")
        date_str = today()

        prompt = f"""Ты — контент-директор кофейни Sunbula (Астана, Казахстан).
Кофейня: уютная, семейная, про осознанное питание, кофе, завтраки, здоровую еду.
Аудитория: молодые люди 22-40 лет, семьи, осознанные потребители.
Тональность: тёплая, живая, честная, без пафоса.

Данные за вчера:
- Выручка: {fmt(total)} ₸
- Чеков: {checks}, средний чек: {fmt(avg)} ₸
- День недели сегодня: {weekday}
- Погода в Астане: {weather}
- Дата: {date_str}

Создай 5 уникальных сторителлинг-историй для Instagram Stories.
Каждая история — это серия из 3-4 слайдов с текстом.
Истории должны быть разными по теме: одна про утро, одна про продукт, одна эмоциональная, одна вовлекающая (вопрос/опрос), одна продающая.
Учитывай погоду и день недели при создании.

Формат каждой истории:
История N — [название]
Слайд 1: [текст]
Слайд 2: [текст]
Слайд 3: [текст]
Слайд 4 (если нужен): [текст/CTA]

Пиши на русском языке. Будь креативным и живым."""

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 2000,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            data = r.json()
        return data["content"][0]["text"]
    except Exception as e:
        return f"🤖 Ошибка генерации: {e}"

# ── УТРЕННЕЕ УВЕДОМЛЕНИЕ ───────────────────────────────────────────────────────
async def send_morning_report():
    try:
        yesterday = (now_dt() - timedelta(days=1)).strftime("%Y-%m-%d")
        rows = sb.table("daily_reports").select("*").eq("date", yesterday).execute()
        report = rows.data[0] if rows.data else {}

        weather = await get_weather()
        stories = await generate_stories(weather, report)

        total    = report.get("total", 0)
        checks   = report.get("checks_count", 0)
        avg      = report.get("avg_check", 0)
        cash_end = report.get("cash_end", 0)

        if report:
            stats = (
                "📊 <b>Итоги вчера (" + yesterday + "):</b>\n"
                "💰 Выручка: <b>" + fmt(total) + " ₸</b>\n"
                "🧾 Чеков: " + str(checks) + "  |  Средний: <b>" + fmt(avg) + " ₸</b>\n"
                "💵 Остаток наличных: <b>" + fmt(cash_end) + " ₸</b>"
            )
        else:
            stats = "📊 Отчёт за вчера не найден"

        sep = "—" * 26
        text = (
            "☀️ <b>Доброе утро, Айторе!</b>\n\n"
            + stats + "\n\n"
            + "🌤 <b>Погода в Астане:</b>\n" + weather + "\n\n"
            + sep + "\n"
            + "🎬 <b>Контент на сегодня:</b>\n\n"
            + stories
        )

        # Отправляем обоим админам
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, text, parse_mode="HTML")
            except Exception as e:
                logging.error(f"Не удалось отправить утренний отчёт {admin_id}: {e}")

        logging.info("✅ Утренний отчёт отправлен")
    except Exception as e:
        logging.error(f"Ошибка утреннего отчёта: {e}")

# ── ПЛАНИРОВЩИК ────────────────────────────────────────────────────────────────
async def scheduler():
    """Ждёт 9:00 по Астане и отправляет утренний отчёт"""
    while True:
        now = now_dt()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logging.info(f"⏰ Следующий отчёт через {int(wait_seconds//3600)}ч {int((wait_seconds%3600)//60)}мин")
        await asyncio.sleep(wait_seconds)
        await send_morning_report()

# ── Run ────────────────────────────────────────────────────────────────────────
async def main():
    logging.info("✅ Sunbula Bot started!")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
