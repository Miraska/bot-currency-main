from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db.requests_database import log_request, get_requests_count_today, get_total_requests_count, get_unique_users_count
from services.requests_service import generate_stats_table_today, generate_full_stats_pdf

router = Router()

STATS_PASSWORD = "Incube116"
ALLOWED_USERS = [123456789, 987654321]  # подставьте нужные ID

class StatsStates(StatesGroup):
    waiting_for_password = State()

@router.message(Command("stats"))
async def cmd_stats(message: Message, state: FSMContext):
    """
    Если пользователь в списке ALLOWED_USERS — сразу показываем статистику.
    Иначе — просим пароль.
    """
    log_request(str(message.from_user.id), message.text)

    if message.from_user.id in ALLOWED_USERS:
        await message.answer("Вы имеете доступ к статистике. Наберите /stats_menu для выбора.")
    else:
        await message.answer("Введите пароль для доступа к статистике:")
        await state.set_state(StatsStates.waiting_for_password)

@router.message(StatsStates.waiting_for_password)
async def msg_stats_password(message: Message, state: FSMContext):
    if message.text.lower() == STATS_PASSWORD.lower() or message.from_user.id in ALLOWED_USERS:
        menu_text = (
        "/stats_counts — показать число запросов сегодня/всего и кол-во уникальных пользователей\n"
        "/stats_pdf — скачать PDF со всей статистикой\n"
        )
        await message.answer(menu_text)
        await state.clear()
    else:
        await message.answer("Неверный пароль. Попробуйте снова.")
    

@router.message(Command("stats_today"))
async def cmd_stats_today(message: Message):
    table_str = generate_stats_table_today()
    await message.answer(f"Запросы за сегодня:\n<pre>{table_str}</pre>", parse_mode="HTML")

@router.message(Command("stats_counts"))
async def cmd_stats_counts(message: Message):
    today_count = get_requests_count_today()
    total_count = get_total_requests_count()
    unique_users = get_unique_users_count()
    text = (
        f"Запросов за сегодня: {today_count}\n"
        f"Запросов всего: {total_count}\n"
        f"Уникальных пользователей: {unique_users}\n"
    )
    await message.answer(text)

@router.message(Command("stats_pdf"))
async def cmd_stats_pdf(message: Message):
    pdf_file = generate_full_stats_pdf()
    await message.answer_document(pdf_file, caption="Полная статистика (PDF)")
