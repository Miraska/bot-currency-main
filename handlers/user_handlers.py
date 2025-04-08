from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from db.database import add_user, update_user_variables, set_process_state

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    add_user(message.from_user.id)
    await message.answer(
        "Привет! Я бот для просмотра курсов и расчётов.\n"
        "Доступные команды:\n"
        "/refresh — сброс переменных\n"
        "/usd, /euro, /cny — посмотреть курсы\n"
        "/view_variables, /set_variable, /calculate — работа с переменными\n"
        "/stats — посмотреть статистику\n"
    )

@router.message(Command("refresh"))
async def cmd_refresh(message: Message):
    default_vars = {
        "royalty": 0.1,
        "delivery": 0.15,
        "payment": 0.12,
        "operational": 0.2,
        "cashless": 0.4,
        "discount": 0.2,
        "aedusdt": 0.3
    }
    update_user_variables(message.from_user.id, default_vars)
    await message.answer("Переменные сброшены к значениям по умолчанию.")


@router.message(Command("clear_state"))
async def cmd_usd(message: Message):
    set_process_state(message.from_user.id, False)
    await message.answer("Состояние сброшено.")