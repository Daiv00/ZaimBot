import asyncio
import os
import re
import secrets
import string
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)

import config


# -----------------------------
# In-memory state only
# -----------------------------

applications = {}
user_to_application = {}


class ApplicationForm(StatesGroup):
    fio = State()
    phone = State()
    birth_date = State()
    address = State()
    passport = State()
    registration = State()
    amount = State()
    term = State()
    bank = State()
    passport_photo = State()
    registration_photo = State()
    selfie = State()
    personal_confirm = State()
    final_confirm = State()


bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def new_id() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "LN-" + "".join(secrets.choice(alphabet) for _ in range(7))


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_IDS


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Подать заявку")],
            [KeyboardButton(text="📋 Мои заявки")],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def confirm_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтверждаю",
                    callback_data="personal_yes",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="personal_no",
                ),
            ]
        ]
    )


def final_keyboard(app_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить заявку",
                    callback_data=f"final_yes:{app_id}",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=f"final_no:{app_id}",
                ),
            ]
        ]
    )


def admin_keyboard(app_id: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🟢 Одобрить",
                    callback_data=f"approve:{app_id}",
                ),
                InlineKeyboardButton(
                    text="🔴 Отказать",
                    callback_data=f"reject:{app_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💸 Выдано",
                    callback_data=f"paid:{app_id}",
                ),
            ],
        ]
    )


def format_application(app: dict) -> str:
    status = {
        "review": "🟡 На рассмотрении",
        "approved": "🟢 Одобрено",
        "rejected": "🔴 Отказ",
        "paid": "💸 Выдано",
    }.get(app["status"], app["status"])

    return (
        f"📄 ЗАЯВКА {app['id']}\n"
        f"Статус: {status}\n\n"
        f"👤 ФИО: {app.get('fio', '-')}\n"
        f"📞 Телефон: {app.get('phone', '-')}\n"
        f"🎂 Дата рождения: {app.get('birth_date', '-')}\n"
        f"🏠 Адрес проживания: {app.get('address', '-')}\n"
        f"🪪 Паспортные данные: {app.get('passport', '-')}\n"
        f"📍 Адрес регистрации: {app.get('registration', '-')}\n"
        f"💰 Сумма займа: {app.get('amount', '-')}\n"
        f"📅 Срок: {app.get('term', '-')}\n"
        f"🏦 Банк и реквизиты: {app.get('bank', '-')}\n\n"
        f"Telegram ID: {app['user_id']}\n"
        f"Создана: {app['created_at']}"
    )


async def safe_delete(path: str | None):
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass


async def send_contract(user_id: int, app: dict):
    Path(config.CONTRACT_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(config.CONTRACT_DIR) / f"{app['id']}.pdf"

    font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    if os.path.exists(font_path):
        pdfmetrics.registerFont(TTFont("DejaVu", font_path))
        if os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont("DejaVuBold", bold_path))
        normal = "DejaVu"
        bold = "DejaVuBold" if os.path.exists(bold_path) else "DejaVu"
    else:
        normal = "Helvetica"
        bold = "Helvetica-Bold"

    c.setFont(bold, 16)
    c.drawString(50, height - 60, "ПРОЕКТ ДОГОВОРА ЗАЙМА")

    y = height - 100
    c.setFont(normal, 10)

    lines = [
        f"Номер заявки: {app['id']}",
        f"Дата: {datetime.now().strftime('%d.%m.%Y')}",
        "",
        f"Заемщик: {app.get('fio', '-')}",
        f"Телефон: {app.get('phone', '-')}",
        f"Дата рождения: {app.get('birth_date', '-')}",
        f"Адрес: {app.get('address', '-')}",
        f"Паспорт: {app.get('passport', '-')}",
        f"Адрес регистрации: {app.get('registration', '-')}",
        f"Сумма займа: {app.get('amount', '-')}",
        f"Срок: {app.get('term', '-')}",
        f"Банк и реквизиты: {app.get('bank', '-')}",
        "",
        "Статус: одобрено.",
        "",
        "Настоящий документ является проектом и требует",
        "юридической проверки и согласования условий.",
    ]

    for line in lines:
        c.drawString(50, y, line[:120])
        y -= 18
        if y < 60:
            c.showPage()
            c.setFont(normal, 10)
            y = height - 60

    c.save()

    await bot.send_document(
        user_id,
        FSInputFile(str(path)),
        caption=f"📄 Проект договора по заявке {app['id']}.",
    )


async def notify_admins(app: dict):
    if not config.ADMIN_CHAT_ID:
        return

    await bot.send_message(
        config.ADMIN_CHAT_ID,
        format_application(app),
        reply_markup=admin_keyboard(app["id"]),
    )

    labels = [
        ("🪪 Фото паспорта", app.get("passport_photo")),
        ("📍 Фото регистрации", app.get("registration_photo")),
        ("🤳 Селфи с паспортом", app.get("selfie")),
    ]

    for caption, path in labels:
        if path and os.path.exists(path):
            await bot.send_document(
                config.ADMIN_CHAT_ID,
                FSInputFile(path),
                caption=f"{caption} — {app['id']}",
            )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Здравствуйте! Здесь можно подать заявку на займ.\n\n"
        "Нажмите «📝 Подать заявку», чтобы начать.",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Заявка отменена.",
        reply_markup=main_keyboard(),
    )


@dp.message(F.text == "📝 Подать заявку")
async def begin(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ApplicationForm.fio)
    await message.answer(
        "Введите ФИО полностью:",
        reply_markup=cancel_keyboard(),
    )


@dp.message(F.text == "📋 Мои заявки")
async def my_applications(message: Message):
    user_apps = [
        a for a in applications.values()
        if a["user_id"] == message.from_user.id
    ]

    if not user_apps:
        await message.answer("У вас пока нет заявок.", reply_markup=main_keyboard())
        return

    text = "📋 Ваши заявки:\n\n"
    for app in user_apps:
        status = {
            "review": "🟡 рассмотрение",
            "approved": "🟢 одобрение",
            "rejected": "🔴 отказ",
            "paid": "💸 выдано",
        }.get(app["status"], app["status"])
        text += f"{app['id']} — {status}\n"

    await message.answer(text, reply_markup=main_keyboard())


@dp.message(ApplicationForm.fio)
async def fio(message: Message, state: FSMContext):
    await state.update_data(fio=message.text)
    await state.set_state(ApplicationForm.phone)
    await message.answer("Введите номер телефона:")


@dp.message(ApplicationForm.phone)
async def phone(message: Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await state.set_state(ApplicationForm.birth_date)
    await message.answer("Введите дату рождения:")


@dp.message(ApplicationForm.birth_date)
async def birth_date(message: Message, state: FSMContext):
    await state.update_data(birth_date=message.text)
    await state.set_state(ApplicationForm.address)
    await message.answer("Введите адрес проживания:")


@dp.message(ApplicationForm.address)
async def address(message: Message, state: FSMContext):
    await state.update_data(address=message.text)
    await state.set_state(ApplicationForm.passport)
    await message.answer("Введите паспортные данные:")


@dp.message(ApplicationForm.passport)
async def passport(message: Message, state: FSMContext):
    await state.update_data(passport=message.text)
    await state.set_state(ApplicationForm.registration)
    await message.answer("Введите адрес регистрации:")


@dp.message(ApplicationForm.registration)
async def registration(message: Message, state: FSMContext):
    await state.update_data(registration=message.text)
    await state.set_state(ApplicationForm.amount)
    await message.answer("Введите сумму займа:")


@dp.message(ApplicationForm.amount)
async def amount(message: Message, state: FSMContext):
    await state.update_data(amount=message.text)
    await state.set_state(ApplicationForm.term)
    await message.answer("Введите срок займа:")


@dp.message(ApplicationForm.term)
async def term(message: Message, state: FSMContext):
    await state.update_data(term=message.text)
    await state.set_state(ApplicationForm.bank)
    await message.answer("Введите банк и реквизиты для выдачи:")


@dp.message(ApplicationForm.bank)
async def bank(message: Message, state: FSMContext):
    await state.update_data(bank=message.text)
    await state.set_state(ApplicationForm.passport_photo)
    await message.answer("Отправьте фото паспорта одним сообщением.")


async def require_photo(message: Message, text: str):
    if not message.photo:
        await message.answer(text)
        return False
    return True


@dp.message(ApplicationForm.passport_photo)
async def passport_photo(message: Message, state: FSMContext):
    if not await require_photo(message, "Нужно отправить именно фото паспорта."):
        return

    file = await bot.get_file(message.photo[-1].file_id)
    Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(config.UPLOAD_DIR) / f"{message.from_user.id}_{secrets.token_hex(4)}_passport.jpg"
    await bot.download_file(file.file_path, destination=str(path))

    await state.update_data(passport_photo=str(path))
    await state.set_state(ApplicationForm.registration_photo)
    await message.answer("Теперь отправьте фото документа о регистрации.")


@dp.message(ApplicationForm.registration_photo)
async def registration_photo(message: Message, state: FSMContext):
    if not await require_photo(message, "Нужно отправить именно фото регистрации."):
        return

    file = await bot.get_file(message.photo[-1].file_id)
    Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(config.UPLOAD_DIR) / f"{message.from_user.id}_{secrets.token_hex(4)}_registration.jpg"
    await bot.download_file(file.file_path, destination=str(path))

    await state.update_data(registration_photo=str(path))
    await state.set_state(ApplicationForm.selfie)
    await message.answer("Теперь отправьте селфи с паспортом.")


@dp.message(ApplicationForm.selfie)
async def selfie(message: Message, state: FSMContext):
    if not await require_photo(message, "Нужно отправить селфи с паспортом."):
        return

    file = await bot.get_file(message.photo[-1].file_id)
    Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    path = Path(config.UPLOAD_DIR) / f"{message.from_user.id}_{secrets.token_hex(4)}_selfie.jpg"
    await bot.download_file(file.file_path, destination=str(path))

    data = await state.get_data()
    data["selfie"] = str(path)

    app_id = new_id()
    app = {
        **data,
        "id": app_id,
        "user_id": message.from_user.id,
        "status": "draft",
        "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
    }
    applications[app_id] = app
    user_to_application[message.from_user.id] = app_id

    await state.update_data(app_id=app_id)
    await state.set_state(ApplicationForm.personal_confirm)

    await message.answer(
        "Проверьте данные заявки:\n\n"
        + format_application(app)
        + "\n\n"
        "Перед отправкой подтвердите согласие на обработку "
        "персональных данных.",
        reply_markup=confirm_keyboard(),
    )


@dp.callback_query(F.data == "personal_no")
async def personal_no(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.answer(
        "Заявка отменена.",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "personal_yes")
async def personal_yes(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    app_id = data.get("app_id")
    app = applications.get(app_id)

    if not app:
        await call.answer("Заявка не найдена.", show_alert=True)
        return

    await state.set_state(ApplicationForm.final_confirm)
    await call.answer()

    await call.message.answer(
        "Последний шаг.\n\n"
        "Нажмите «Отправить заявку», чтобы передать заявку "
        "администратору.",
        reply_markup=final_keyboard(app_id),
    )


@dp.callback_query(F.data.startswith("final_no:"))
async def final_no(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.answer(
        "Заявка отменена.",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data.startswith("final_yes:"))
async def final_yes(call: CallbackQuery, state: FSMContext):
    app_id = call.data.split(":", 1)[1]
    app = applications.get(app_id)

    if not app:
        await call.answer("Заявка не найдена.", show_alert=True)
        return

    app["status"] = "review"

    await notify_admins(app)
    await state.clear()

    await call.answer("Заявка отправлена")
    await call.message.answer(
        f"✅ Заявка {app_id} отправлена на рассмотрение.",
        reply_markup=main_keyboard(),
    )


async def change_status(call: CallbackQuery, app_id: str, status: str):
    if not is_admin(call.from_user.id):
        await call.answer("Нет доступа.", show_alert=True)
        return

    app = applications.get(app_id)
    if not app:
        await call.answer(
            "Заявка отсутствует в памяти текущего запуска бота.",
            show_alert=True,
        )
        return

    app["status"] = status

    status_text = {
        "approved": "🟢 Ваша заявка одобрена.",
        "rejected": "🔴 По вашей заявке получен отказ.",
        "paid": "💸 По вашей заявке отмечена выдача займа.",
    }[status]

    await bot.send_message(app["user_id"], status_text)

    if status == "approved":
        await send_contract(app["user_id"], app)
        await bot.send_message(
            app["user_id"],
            f"📄 Договор также доступен командой /contract_{app_id}",
        )

    await call.answer("Статус изменён")

    try:
        await call.message.edit_text(
            format_application(app),
            reply_markup=admin_keyboard(app_id),
        )
    except Exception:
        pass


@dp.callback_query(F.data.startswith("approve:"))
async def approve(call: CallbackQuery):
    await change_status(call, call.data.split(":", 1)[1], "approved")


@dp.callback_query(F.data.startswith("reject:"))
async def reject(call: CallbackQuery):
    await change_status(call, call.data.split(":", 1)[1], "rejected")


@dp.callback_query(F.data.startswith("paid:"))
async def paid(call: CallbackQuery):
    await change_status(call, call.data.split(":", 1)[1], "paid")


def command_app_id(text: str, command: str):
    prefix = f"/{command}_"
    if text.startswith(prefix):
        return text[len(prefix):].strip()
    return None


@dp.message(Command("admin"))
async def admin(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    if not applications:
        await message.answer("Заявок в памяти текущего запуска нет.")
        return

    items = list(applications.values())[-50:]
    text = "📋 Заявки за текущий запуск:\n\n"
    for app in reversed(items):
        text += f"{app['id']} — {app['status']} — {app['fio']}\n"

    await message.answer(text)


@dp.message(F.text.startswith("/approve_"))
async def approve_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    app_id = command_app_id(message.text, "approve")
    app = applications.get(app_id)
    if not app:
        await message.answer("Заявка не найдена в памяти текущего запуска.")
        return
    app["status"] = "approved"
    await bot.send_message(app["user_id"], "🟢 Ваша заявка одобрена.")
    await send_contract(app["user_id"], app)
    await message.answer(f"Заявка {app_id}: одобрено.")


@dp.message(F.text.startswith("/reject_"))
async def reject_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    app_id = command_app_id(message.text, "reject")
    app = applications.get(app_id)
    if not app:
        await message.answer("Заявка не найдена в памяти текущего запуска.")
        return
    app["status"] = "rejected"
    await bot.send_message(app["user_id"], "🔴 По вашей заявке получен отказ.")
    await message.answer(f"Заявка {app_id}: отказ.")


@dp.message(F.text.startswith("/paid_"))
async def paid_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    app_id = command_app_id(message.text, "paid")
    app = applications.get(app_id)
    if not app:
        await message.answer("Заявка не найдена в памяти текущего запуска.")
        return
    app["status"] = "paid"
    await bot.send_message(app["user_id"], "💸 По вашей заявке отмечена выдача займа.")
    await message.answer(f"Заявка {app_id}: выдача отмечена.")


@dp.message(F.text.startswith("/case_"))
async def case_command(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return
    app_id = command_app_id(message.text, "case")
    app = applications.get(app_id)
    if not app:
        await message.answer("Заявка не найдена в памяти текущего запуска.")
        return

    await message.answer(format_application(app))


@dp.message(F.text.startswith("/contract_"))
async def contract_command(message: Message):
    app_id = command_app_id(message.text, "contract")
    app = applications.get(app_id)
    if not app:
        await message.answer(
            "Эта заявка не найдена в памяти текущего запуска. "
            "Если бот перезапускался, старые данные доступны в админ-чате."
        )
        return

    if app["user_id"] != message.from_user.id and not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await send_contract(message.from_user.id, app)


@dp.message()
async def fallback(message: Message):
    await message.answer(
        "Используйте кнопки меню.",
        reply_markup=main_keyboard(),
    )


# -----------------------------
# FastAPI / Render webhook
# -----------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not config.ADMIN_CHAT_ID:
        raise RuntimeError("ADMIN_CHAT_ID is not set")
    if not config.RENDER_EXTERNAL_URL:
        raise RuntimeError(
            "RENDER_EXTERNAL_URL is not available. "
            "Add your Render service URL manually as RENDER_EXTERNAL_URL."
        )

    webhook_url = f"{config.RENDER_EXTERNAL_URL}{config.WEBHOOK_PATH}"

    await bot.set_webhook(
        webhook_url,
        secret_token=config.WEBHOOK_SECRET or None,
        allowed_updates=dp.resolve_used_update_types(),
    )

    yield

    await bot.delete_webhook()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    return {"ok": True}


@app.post(config.WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if config.WEBHOOK_SECRET:
        if x_telegram_bot_api_secret_token != config.WEBHOOK_SECRET:
            raise HTTPException(status_code=403, detail="Invalid secret")

    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}
