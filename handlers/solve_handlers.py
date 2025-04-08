import json
from aiogram import Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from db.database import get_user_variables, update_user_variables
from keyboards.user_keyboards import buttons
from db.requests_database import log_request
from services.parser_service import ParserService

router = Router()

parser_service = ParserService()

class SolveStates(StatesGroup):
    waiting_for_variable = State()
    waiting_for_value_variable = State()
    waiting_for_calc_value = State()

@router.message(Command("view_variables"))
async def cmd_view_vars(message: Message):
    log_request(str(message.from_user.id), message.text)
    user_vars = get_user_variables(message.from_user.id)
    if not user_vars:
        await message.answer("У вас нет сохранённых переменных.")
        return
    text = "Текущие переменные:\n" + "\n".join(f"{k}: {v}" for k, v in user_vars.items())
    await message.answer(text)

@router.message(Command("set_variable"))
async def cmd_set_variable(message: Message, state: FSMContext):
    log_request(str(message.from_user.id), message.text)
    await state.set_state(SolveStates.waiting_for_variable)
    await message.answer("Выберите имя переменной:", reply_markup=buttons)

@router.callback_query(SolveStates.waiting_for_variable)
async def callback_var_selection(callback: CallbackQuery, state: FSMContext):
    var_name = callback.data
    await state.update_data(var_name=var_name)
    await state.set_state(SolveStates.waiting_for_value_variable)
    await callback.message.answer(f"Введите новое значение для переменной '{var_name}'")
    await callback.answer()

@router.message(SolveStates.waiting_for_value_variable)
async def msg_var_value(message: Message, state: FSMContext):
    data = await state.get_data()
    var_name = data.get("var_name")
    try:
        var_value = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Некорректное число. Повторите ввод.")
        return

    user_vars = get_user_variables(message.from_user.id) or {}
    user_vars[var_name] = var_value
    update_user_variables(message.from_user.id, user_vars)

    await message.answer(f"Переменная '{var_name}' обновлена на {var_value}.")
    await state.set_state(SolveStates.waiting_for_variable)
    await message.answer("Выберите имя переменной:", reply_markup=buttons)

@router.message(Command("calculate"))
async def cmd_calculate(message: Message, state: FSMContext):
    log_request(str(message.from_user.id), message.text)
    await state.set_state(SolveStates.waiting_for_calc_value)
    await message.answer("Введите значение для сделки (t).")

@router.message(SolveStates.waiting_for_calc_value)
async def msg_calc_deal(message: Message, state: FSMContext):
    try:
        t = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Некорректное число. Повторите ввод.")
        return

    await state.clear()
    wait_msg = await message.answer("Выполняем расчёт...")

    try:
        # Получаем данные и преобразуем их в числа
        garantex = float(parser_service.get_garantex_rate("usdtrub"))
        profinance = float(await parser_service.get_profinance_rate(
            url="https://www.profinance.ru/chart/usdrub/",
            selector="#b_29"
        ))

        if not isinstance(garantex, (int, float)):
            garantex = float(garantex)

        if not isinstance(profinance, (int, float)):
            profinance = float(profinance)

        # Выполняем расчёты
        y = profinance + (profinance / 100 * t)

        user_vars = get_user_variables(message.from_user.id) or {}
        total_vars = sum(user_vars.values())

        result = (((garantex - 0.1) - y) * (100 / profinance)) - total_vars
        result = round(result, 4)

        # Формируем результат
        text = (
            f"Сумма переменных: {total_vars.__round__(3)}\n"
            f"Garantex: {garantex}\n"
            f"Profinance: {profinance}\n"
            f"t: {t}\n"
            f"y: {y}\n"
            f"Сделка: {result}%"
        )
        await wait_msg.edit_text(text)

    except ValueError as e:
        await wait_msg.edit_text(f"Ошибка при преобразовании данных: {e}")
    except Exception as e:
        await wait_msg.edit_text(f"Ошибка при расчёте: {e}")
