
import os, re, asyncio
from datetime import datetime
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, FSInputFile, Update
)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

import config

pool = None
bot = Bot(config.BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

STATUS = {
    "review": "🟡 На рассмотрении",
    "approved": "🟢 Одобрено",
    "rejected": "🔴 Отказано",
    "paid": "💸 Выдано",
}

class LoanForm(StatesGroup):
    full_name=State(); phone=State(); birth_date=State(); address=State()
    passport_data=State(); registration_address=State(); amount=State()
    term_months=State(); bank_details=State(); passport_photo=State()
    registration_photo=State(); selfie_photo=State(); personal_confirm=State()
    final_confirm=State()

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS applications (
 id SERIAL PRIMARY KEY,
 telegram_user_id BIGINT NOT NULL,
 telegram_username TEXT,
 full_name TEXT NOT NULL,
 phone TEXT NOT NULL,
 birth_date TEXT NOT NULL,
 address TEXT NOT NULL,
 passport_data TEXT NOT NULL,
 registration_address TEXT NOT NULL,
 amount INTEGER NOT NULL,
 term_months INTEGER NOT NULL,
 bank_details TEXT NOT NULL,
 passport_photo TEXT,
 registration_photo TEXT,
 selfie_photo TEXT,
 personal_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
 final_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
 status TEXT NOT NULL DEFAULT 'review',
 rejection_reason TEXT,
 contract_path TEXT,
 paid_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
    await pool.execute(CREATE_SQL)
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в Render Environment.")
    if not config.RENDER_EXTERNAL_URL:
        raise RuntimeError("RENDER_EXTERNAL_URL не задан.")
    webhook = config.RENDER_EXTERNAL_URL.rstrip("/") + config.WEBHOOK_PATH
    await bot.set_webhook(
        webhook,
        secret_token=config.WEBHOOK_SECRET or None,
        drop_pending_updates=True,
    )
    yield
    await bot.delete_webhook()
    await pool.close()
    await bot.session.close()

app = FastAPI(title="Loan Telegram Bot", lifespan=lifespan)

@app.get("/")
async def root():
    return {"ok": True, "service": "loan-telegram-bot"}

@app.get("/health")
async def health():
    return {"ok": True}

@app.post(config.WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if config.WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != config.WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Forbidden")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📝 Подать заявку")],
        [KeyboardButton(text="📋 Мои заявки")]
    ], resize_keyboard=True)

def confirm_kb(prefix):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтверждаю", callback_data=f"{prefix}:yes")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"{prefix}:no")]
    ])

def admin_kb(i):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 Одобрить", callback_data=f"approve:{i}"),
         InlineKeyboardButton(text="🔴 Отказать", callback_data=f"reject:{i}")],
        [InlineKeyboardButton(text="💸 Выдано", callback_data=f"paid:{i}")]
    ])

def is_admin(uid): return uid in config.ADMIN_IDS

async def get_app(i):
    return await pool.fetchrow("SELECT * FROM applications WHERE id=$1", i)

def create_contract(a):
    os.makedirs(config.CONTRACT_DIR, exist_ok=True)
    path=f"{config.CONTRACT_DIR}/contract_{a['id']}.pdf"
    c=canvas.Canvas(path,pagesize=A4); y=A4[1]-60
    for line in [
        config.COMPANY_NAME,"","ПРОЕКТ ДОГОВОРА ЗАЙМА","",
        f"Номер заявки: {a['id']}",f"Дата: {datetime.now():%d.%m.%Y}","",
        f"Заемщик: {a['full_name']}",f"Дата рождения: {a['birth_date']}",
        f"Сумма займа: {a['amount']} руб.",f"Срок: {a['term_months']} мес.",
        f"Банк/реквизиты: {a['bank_details']}","",
        "Документ является проектом договора и требует юридической проверки."
    ]:
        c.drawString(50,y,line[:110]); y-=20
    c.save(); return path

@router.message(Command("start"))
async def start(m:Message,state:FSMContext):
    await state.clear()
    await m.answer("Здравствуйте!\n\nЗдесь можно подать заявку на займ и отслеживать её статус.",reply_markup=main_kb())

@router.message(F.text=="📝 Подать заявку")
async def begin(m:Message,state:FSMContext):
    await state.clear(); await state.set_state(LoanForm.full_name); await m.answer("Введите ФИО:")

async def text_field(m,s,next_state,key,prompt):
    await s.update_data(**{key:m.text.strip()}); await s.set_state(next_state); await m.answer(prompt)

@router.message(LoanForm.full_name)
async def f1(m,s): await text_field(m,s,LoanForm.phone,"full_name","Введите номер телефона:")
@router.message(LoanForm.phone)
async def f2(m,s): await text_field(m,s,LoanForm.birth_date,"phone","Введите дату рождения (ДД.ММ.ГГГГ):")
@router.message(LoanForm.birth_date)
async def f3(m,s): await text_field(m,s,LoanForm.address,"birth_date","Введите адрес проживания:")
@router.message(LoanForm.address)
async def f4(m,s): await text_field(m,s,LoanForm.passport_data,"address","Введите паспортные данные:")
@router.message(LoanForm.passport_data)
async def f5(m,s): await text_field(m,s,LoanForm.registration_address,"passport_data","Введите адрес регистрации:")
@router.message(LoanForm.registration_address)
async def f6(m,s): await text_field(m,s,LoanForm.amount,"registration_address","Введите сумму займа в рублях:")

@router.message(LoanForm.amount)
async def f7(m,s):
    try: v=int(m.text.replace(" ","").replace(",","")); assert v>0
    except: return await m.answer("Введите положительное целое число.")
    await s.update_data(amount=v); await s.set_state(LoanForm.term_months); await m.answer("Введите срок в месяцах:")

@router.message(LoanForm.term_months)
async def f8(m,s):
    try: v=int(m.text); assert v>0
    except: return await m.answer("Введите количество месяцев целым числом.")
    await s.update_data(term_months=v); await s.set_state(LoanForm.bank_details); await m.answer("Введите банк и реквизиты:")

@router.message(LoanForm.bank_details)
async def f9(m,s):
    await s.update_data(bank_details=m.text.strip()); await s.set_state(LoanForm.passport_photo); await m.answer("📷 Отправьте фото паспорта:")

async def save_photo(m,s,key):
    if not m.photo:
        await m.answer("Отправьте именно фотографию."); return False
    folder=f"{config.UPLOAD_DIR}/{m.from_user.id}"; os.makedirs(folder,exist_ok=True)
    p=f"{folder}/{key}_{m.photo[-1].file_id}.jpg"
    await m.bot.download(m.photo[-1],destination=p)
    await s.update_data(**{key:p}); return True

@router.message(LoanForm.passport_photo)
async def p1(m,s):
    if await save_photo(m,s,"passport_photo"):
        await s.set_state(LoanForm.registration_photo); await m.answer("📷 Отправьте фото регистрации:")

@router.message(LoanForm.registration_photo)
async def p2(m,s):
    if await save_photo(m,s,"registration_photo"):
        await s.set_state(LoanForm.selfie_photo); await m.answer("🤳 Отправьте селфи с паспортом:")

@router.message(LoanForm.selfie_photo)
async def p3(m,s):
    if await save_photo(m,s,"selfie_photo"):
        await s.set_state(LoanForm.personal_confirm)
        await m.answer("Подтвердите согласие на обработку персональных данных.",reply_markup=confirm_kb("personal"))

@router.callback_query(F.data=="personal:yes")
async def personal(c,s):
    await s.update_data(personal_confirmed=True); d=await s.get_data()
    text=(f"📋 Проверьте заявку\n\nФИО: {d['full_name']}\nТелефон: {d['phone']}\n"
          f"Дата рождения: {d['birth_date']}\nАдрес: {d['address']}\nПаспорт: {d['passport_data']}\n"
          f"Регистрация: {d['registration_address']}\nСумма: {d['amount']} руб.\n"
          f"Срок: {d['term_months']} мес.\nБанк: {d['bank_details']}\n\nПодтвердить отправку?")
    await s.set_state(LoanForm.final_confirm); await c.message.edit_text(text,reply_markup=confirm_kb("final")); await c.answer()

@router.callback_query(F.data=="personal:no")
async def personal_no(c,s): await s.clear(); await c.message.edit_text("Заявка отменена."); await c.answer()

@router.callback_query(F.data=="final:no")
async def final_no(c,s): await s.clear(); await c.message.edit_text("Заявка не отправлена."); await c.answer()

@router.callback_query(F.data=="final:yes")
async def final_yes(c,s):
    d=await s.get_data()
    row=await pool.fetchrow("""INSERT INTO applications
    (telegram_user_id,telegram_username,full_name,phone,birth_date,address,passport_data,
    registration_address,amount,term_months,bank_details,passport_photo,registration_photo,
    selfie_photo,personal_confirmed,final_confirmed,status)
    VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,TRUE,TRUE,'review')
    RETURNING id""",
    c.from_user.id,c.from_user.username,d["full_name"],d["phone"],d["birth_date"],d["address"],
    d["passport_data"],d["registration_address"],d["amount"],d["term_months"],d["bank_details"],
    d.get("passport_photo"),d.get("registration_photo"),d.get("selfie_photo"))
    i=row["id"]; await s.clear()
    await c.message.edit_text(f"✅ Заявка #{i} принята.\nСтатус: 🟡 На рассмотрении.")
    if config.NOTIFY_CHAT_ID:
        await c.bot.send_message(config.NOTIFY_CHAT_ID,
            f"🆕 Новая заявка #{i}\n\nФИО: {d['full_name']}\nТелефон: {d['phone']}\n"
            f"Сумма: {d['amount']} руб.\nСрок: {d['term_months']} мес.\n\n"
            f"/approve_{i}\n/reject_{i}\n/paid_{i}\n/case_{i}",reply_markup=admin_kb(i))
    await c.answer()

@router.message(F.text=="📋 Мои заявки")
async def mine(m):
    rows=await pool.fetch("SELECT * FROM applications WHERE telegram_user_id=$1 ORDER BY id DESC",m.from_user.id)
    if not rows: return await m.answer("📋 Заявок нет.")
    await m.answer("\n\n".join(f"#{a['id']} — {STATUS.get(a['status'],a['status'])}\nСумма: {a['amount']} руб.\nСрок: {a['term_months']} мес." for a in rows))

async def set_status(i,status):
    a=await get_app(i)
    if not a: return False,"Заявка не найдена."
    path=a["contract_path"]
    if status=="approved": path=create_contract(a)
    paid=a["paid_at"] or (datetime.now() if status=="paid" else None)
    await pool.execute("UPDATE applications SET status=$1,contract_path=$2,paid_at=$3 WHERE id=$4",status,path,paid,i)
    try:
        extra=f"\n\nДоговор: /contract_{i}" if status=="approved" else ""
        await bot.send_message(a["telegram_user_id"],f"Заявка #{i}: {STATUS[status]}{extra}")
    except Exception: pass
    return True,STATUS[status]

async def show_case(m,i):
    if not is_admin(m.from_user.id): return
    a=await get_app(i)
    if not a: return await m.answer("Заявка не найдена.")
    await m.answer(f"📄 Выписка #{i}\n\nTelegram ID: {a['telegram_user_id']}\nUsername: @{a['telegram_username'] or '-'}\n"
        f"ФИО: {a['full_name']}\nТелефон: {a['phone']}\nДата рождения: {a['birth_date']}\n"
        f"Адрес: {a['address']}\nПаспорт: {a['passport_data']}\nРегистрация: {a['registration_address']}\n"
        f"Сумма: {a['amount']}\nСрок: {a['term_months']}\nБанк: {a['bank_details']}\n"
        f"Статус: {STATUS.get(a['status'],a['status'])}\n"
        f"Фото паспорта: {bool(a['passport_photo'])}\nФото регистрации: {bool(a['registration_photo'])}\nСелфи: {bool(a['selfie_photo'])}")

@router.message(Command("admin"))
async def admin(m):
    if not is_admin(m.from_user.id): return
    rows=await pool.fetch("SELECT * FROM applications ORDER BY id DESC LIMIT 50")
    if not rows: return await m.answer("Заявок нет.")
    for a in rows:
        await m.answer(f"Заявка #{a['id']}\n\nФИО: {a['full_name']}\nТелефон: {a['phone']}\n"
                       f"Сумма: {a['amount']} руб.\nСрок: {a['term_months']} мес.\n"
                       f"Статус: {STATUS.get(a['status'],a['status'])}",reply_markup=admin_kb(a["id"]))

@router.message(F.text.regexp(r"^/(approve|reject|paid|case)_\d+$"))
async def admin_cmd(m):
    if not is_admin(m.from_user.id): return
    x=re.match(r"^/(approve|reject|paid|case)_(\d+)$",m.text)
    action,i=x.group(1),int(x.group(2))
    if action=="case": return await show_case(m,i)
    ok,res=await set_status(i,{"approve":"approved","reject":"rejected","paid":"paid"}[action])
    await m.answer(res if not ok else f"Заявка #{i}: {res}")

@router.callback_query(F.data.startswith(("approve:","reject:","paid:")))
async def admin_buttons(c):
    if not is_admin(c.from_user.id): return await c.answer("Нет доступа.",show_alert=True)
    action,i=c.data.split(":"); ok,res=await set_status(int(i),{"approve":"approved","reject":"rejected","paid":"paid"}[action])
    await c.answer(res if ok else "Ошибка"); await c.message.answer(f"Заявка #{i}: {res}")

@router.message(F.text.regexp(r"^/contract_\d+$"))
async def contract(m):
    i=int(re.search(r"\d+",m.text).group()); a=await get_app(i)
    if not a or a["telegram_user_id"]!=m.from_user.id: return await m.answer("Заявка не найдена.")
    if a["status"] not in ("approved","paid"): return await m.answer("Договор доступен после одобрения.")
    path=a["contract_path"] or create_contract(a)
    await pool.execute("UPDATE applications SET contract_path=$1 WHERE id=$2",path,i)
    await m.answer_document(FSInputFile(path),caption=f"Проект договора по заявке #{i}")
