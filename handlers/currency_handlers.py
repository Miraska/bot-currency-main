import datetime
import pytz
from aiogram import Router
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

import asyncio

from db.database import get_process_state, set_process_state
from services.parser_service import ParserService
from services.updater_instance import investing_updater
from typing import Optional

router = Router()
parser_service = ParserService()

def build_currency_table(
    title: str,
    investing: Optional[str],
    cbr_today: Optional[str],
    cbr_tomorrow: Optional[str],
    profinance: Optional[str],
    moex: Optional[str],
    abcex: Optional[str] = None,
    grinex: Optional[str] = None,
    tranding_view: Optional[str] = None,
) -> str:
    """
    Формируем текстовую "таблицу" по курсам.
    """
    tz = pytz.timezone("Europe/Moscow")
    now_str = datetime.datetime.now(tz).strftime("%d.%m.%Y %H:%M")

    def to_str(val):
        return val if val else "нет"

    text = (
        f"<b>{title}</b> на {now_str} (MSK)\n"
        f"<pre>"
        f"Investing      | {to_str(investing)}\n"
        f"CBR (today)    | {to_str(cbr_today)}\n"
        f"CBR (tomorrow) | {to_str(cbr_tomorrow)}\n"
        f"ProFinance     | {to_str(profinance)}\n"
        f"MOEX           | {to_str(moex)}\n"
    )

    if "USD" in title.upper():
        text += (
            f"ABCEX          | {to_str(abcex)}\n"
            f"Grinex         | {to_str(grinex)} USDT/RUB\n"
            f"TradingView    | {to_str(tranding_view)} GOLD/USD\n"
        )
    elif "EUR" in title.upper():
        # Для евро в примере ставим XE как abcex / grinex
        # (по коду ниже: abcex=xe_euro_usd, grinex=xe_usd_euro)
        text += (
            f"XE             | {to_str(abcex)} EURO/USD\n"
            f"XE             | {to_str(grinex)} USD/EURO\n"
        )
    elif "CNY" in title.upper():
        # Для юаней в примере ставим XE как abcex / grinex
        # (по коду ниже: abcex=xe_cny_usd, grinex=xe_usd_cny)
        text += (
            f"XE             | {to_str(abcex)} USD/CNY\n"
            f"XE             | {to_str(grinex)} CNY/USD\n"
        )

    text += f"</pre>"
    return text

async def edit_message_if_changed(message: Message, new_text: str, old_text: str) -> str:
    """
    Редактируем сообщение только при изменении текста, чтобы избежать ошибки "message is not modified".
    Возвращаем установленный текст.
    """
    if new_text != old_text:
        await message.edit_text(new_text, parse_mode="HTML")
        return new_text
    return old_text

@router.message(Command("usd"))
async def cmd_usd(message: Message):
    """
    Команда /usd — собираем данные по USD/RUB последовательно,
    чтобы не загружать все сайты разом.
    """
    if get_process_state(message.from_user.id):
        await message.reply("У вас уже обрабатывается запрос.")
        return

    set_process_state(message.from_user.id, True)
    wait_msg = await message.answer("Начинаем сбор данных по USD/RUB...")

    old_table_text = ""
    # Изначальное пустое состояние
    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=None,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None,
        abcex=None,
        grinex=None,
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 1. Курс с Investing (берём из нашего investing_updater)
    invest_rate = investing_updater.cached_usd_rate
    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None,
        abcex=None,
        grinex=None,
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    if invest_rate:
        try:
            file_photo = FSInputFile(investing_updater.cached_usd_screenshot)
            await message.answer_photo(file_photo, caption="Скриншот Investing (USD/RUB)")
        except Exception as e:
            print(f"Не удалось отправить скриншот (USD): {e}")

    # 2. CBR (requests)
    try:
        parser_service.update_usd_cbr_rates()
        cbr_today = parser_service.get_cbr_today_rate("USD")
        cbr_tomorrow = parser_service.get_cbr_tomorrow_rate("USD")
    except Exception as e:
        print(f"Ошибка CBR USD: {e}")
        cbr_today = None
        cbr_tomorrow = None

    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=None,
        moex=None,
        abcex=None,
        grinex=None,
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 3. ProFinance
    profinance_rate = await parser_service.get_profinance_rate(
        url="https://www.profinance.ru/chart/usdrub/",
        selector="#app > v-app > div > div > div > table > tbody > tr:nth-child(1) > td:nth-child(2)"
    )
    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=None,
        abcex=None,
        grinex=None,
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 4. MOEX
    moex_rate = await parser_service.get_moex_rate(
        url="https://www.moex.com/ru/derivatives/currency-rate.aspx?currency=USD_RUB",
        selector="#app > div:nth-child(2) > div.ui-container.-default > div > div.ui-table > div.ui-table__container > table > tbody > tr:nth-child(1) > td:nth-child(2)"
    )
    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=None,
        grinex=None,
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 5. Grinex
    grinex_rate = await parser_service.get_grinex_usd_rate()
    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=None,
        grinex=grinex_rate,
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 6. TradingView
    tranding_view = await parser_service.get_tradingview_usd(
        url="https://www.tradingview.com/symbols/XAUUSD/",
        selector="//span[contains(@class, 'last-JWoJqCpY js-symbol-last')]"
    )
    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=None,
        grinex=grinex_rate,
        tranding_view=tranding_view
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 7. ABCEX (синхронный)
    abcex = None
    try:
        abcex = parser_service.get_abcex_rate(
            "https://abcex.io/api/v1/exchange/public/market-data/order-book/depth?marketId=USDTRUB&lang=ru"
        )
    except Exception as e:
        print(f"Ошибка ABCEX USD: {e}")

    table_text = build_currency_table(
        title="Курсы USD/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=abcex,
        grinex=grinex_rate,
        tranding_view=tranding_view
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    set_process_state(message.from_user.id, False)

    await message.answer("Можете дальше отправлять команды.")

@router.message(Command("euro"))
async def cmd_euro(message: Message):
    """
    Команда /euro — сбор данных по EUR/RUB последовательно.
    """
    if get_process_state(message.from_user.id):
        await message.reply("У вас уже обрабатывается запрос.")
        return

    set_process_state(message.from_user.id, True)
    wait_msg = await message.answer("Начинаем сбор данных по EUR/RUB...")

    old_table_text = ""
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=None,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 1. Investing
    invest_rate = investing_updater.cached_eur_rate
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=invest_rate,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    if invest_rate:
        try:
            file_photo = FSInputFile(investing_updater.cached_eur_screenshot)
            await message.answer_photo(file_photo, caption="Скриншот Investing (EUR/RUB)")
        except Exception as e:
            print(f"Не удалось отправить скриншот (EUR): {e}")

    # 2. CBR
    try:
        parser_service.update_eur_cbr_rates()
        cbr_today = parser_service.get_cbr_today_rate("EUR")
        cbr_tomorrow = parser_service.get_cbr_tomorrow_rate("EUR")
    except Exception as e:
        print(f"Ошибка CBR EUR: {e}")
        cbr_today, cbr_tomorrow = None, None

    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=None,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 3. Profinance
    profinance_rate = await parser_service.get_profinance_rate(
        url="https://www.profinance.ru/chart/eurrub/",
        selector="#b_30"
    )
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 4. MOEX
    moex_rate = await parser_service.get_moex_rate(
        url="https://www.moex.com/ru/derivatives/currency-rate.aspx?currency=EUR_RUB",
        selector="#app > div:nth-child(2) > div.ui-container.-default > div > div.ui-table > div.ui-table__container > table > tbody > tr:nth-child(1) > td:nth-child(2)"
    )
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 5. XE (две async-функции последовательно)
    xe_euro_usd = await parser_service.get_xe_rate_euro_dollar()  # "1 EUR = X USD"
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=xe_euro_usd,
        grinex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    xe_usd_euro = await parser_service.get_xe_rate_dollar_euro()  # "1 USD = X EUR"
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=xe_euro_usd,
        grinex=xe_usd_euro
    )
    await edit_message_if_changed(wait_msg, table_text, old_table_text)

    set_process_state(message.from_user.id, False)
    await message.answer("Можете дальше отправлять команды.")

@router.message(Command("cny"))
async def cmd_cny(message: Message):
    """
    Команда /cny — сбор данных по CNY/RUB последовательно.
    """
    if get_process_state(message.from_user.id):
        await message.reply("У вас уже обрабатывается запрос.")
        return

    set_process_state(message.from_user.id, True)
    wait_msg = await message.answer("Начинаем сбор данных по CNY/RUB...")

    old_table_text = ""
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=None,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 1. Investing
    invest_rate = investing_updater.cached_cny_rate
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=invest_rate,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    if invest_rate:
        try:
            file_photo = FSInputFile(investing_updater.cached_cny_screenshot)
            await message.answer_photo(file_photo, caption="Скриншот Investing (CNY/RUB)")
        except Exception as e:
            print(f"Не удалось отправить скриншот (CNY): {e}")

    # 2. CBR
    try:
        parser_service.update_cny_cbr_rates()
        cbr_today = parser_service.get_cbr_today_rate("CNY")
        cbr_tomorrow = parser_service.get_cbr_tomorrow_rate("CNY")
    except Exception as e:
        print(f"Ошибка CBR CNY: {e}")
        cbr_today, cbr_tomorrow = None, None

    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=None,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 3. ProFinance
    profinance_rate = await parser_service.get_profinance_rate(
        url="https://www.profinance.ru/chart/cnyrub/",
        selector="#b_CNY_RUB"
    )
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 4. MOEX
    moex_rate = await parser_service.get_moex_rate(
        url="https://www.moex.com/ru/derivatives/currency-rate.aspx?currency=CNY_RUB",
        selector="#app > div:nth-child(2) > div.ui-container.-default > div > div.ui-table > div.ui-table__container > table > tbody > tr:nth-child(1) > td:nth-child(2)"
    )
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # 5. XE (две async-функции) – последовательно
    xe_usd_cny = await parser_service.get_xe_rate_usd_yuan()  # "1 USD = X CNY"
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=xe_usd_cny,
        grinex=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    xe_cny_usd = await parser_service.get_xe_rate_yuan_usd()  # "1 CNY = X USD"
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=invest_rate,
        cbr_today=cbr_today,
        cbr_tomorrow=cbr_tomorrow,
        profinance=profinance_rate,
        moex=moex_rate,
        abcex=xe_cny_usd,
        grinex=xe_usd_cny
    )
    await edit_message_if_changed(wait_msg, table_text, old_table_text)

    set_process_state(message.from_user.id, False)
    await message.answer("Можете дальше отправлять команды.")
