import datetime
import pytz
import asyncio

from aiogram import Router
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command

# Ваши внутренние модули
from db.database import get_process_state, set_process_state
from services.parser_service import ParserService
from services.updater_instance import investing_updater

router = Router()
parser_service = ParserService()

def build_currency_table(
    title: str,
    investing: str | None,
    cbr_today: str | None,
    cbr_tomorrow: str | None,
    profinance: str | None,
    moex: str | None,
    abcex: str | None = None,
    grinex: str | None = None,
    tranding_view: str | None = None,
) -> str:
    """
    Формируем текстовую таблицу для вывода в Telegram.
    """
    tz = pytz.timezone("Europe/Moscow")
    now_str = datetime.datetime.now(tz).strftime("%d.%m.%Y %H:%M")

    def to_str(v):
        return v if v else "нет"

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
        text += (
            f"XE (1 € -> $)  | {to_str(abcex)}\n"
            f"XE (1 $ -> €)  | {to_str(grinex)}\n"
        )
    elif "CNY" in title.upper():
        text += (
            f"XE (1 $ -> ¥)  | {to_str(abcex)}\n"
            f"XE (1 ¥ -> $)  | {to_str(grinex)}\n"
        )

    text += "</pre>"
    return text

async def edit_message_if_changed(message: Message, new_text: str, old_text: str) -> str:
    """
    Редактируем Telegram-сообщение только если содержимое действительно изменилось,
    чтобы избежать "message is not modified".
    Возвращаем итоговый текст, который остался в сообщении.
    """
    if new_text != old_text:
        await message.edit_text(new_text, parse_mode="HTML")
        return new_text
    return old_text


@router.message(Command("usd"))
async def cmd_usd(message: Message):
    """
    Команда /usd — параллельная загрузка курсов USD/RUB из разных источников
    и динамическое обновление сообщения после каждого готового результата.
    """
    if get_process_state(message.from_user.id):
        await message.reply("У вас уже обрабатывается запрос.")
        return
    set_process_state(message.from_user.id, True)

    wait_msg = await message.answer("Начинаем сбор данных по USD/RUB...")

    await parser_service.init_browser()
    await parser_service.init_browser_context(use_proxy=True)

    old_table_text = ""
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

    # -- Параллельные задачи --
    async def get_investing_usd():
        return investing_updater.cached_usd_rate

    investing_task = asyncio.create_task(get_investing_usd())

    profinance_task = asyncio.create_task(
        parser_service.get_profinance_rate(
            url="https://www.profinance.ru/chart/usdrub/",
            selector="#app > v-app > div > div > div > table > tbody > tr:nth-child(1) > td:nth-child(2)"
        )
    )

    moex_task = asyncio.create_task(
        parser_service.get_moex_rate(
            url="https://www.moex.com/ru/derivatives/currency-rate.aspx?currency=USD_RUB",
            selector="#app > div:nth-child(2) > div.ui-container.-default > div > div.ui-table > div.ui-table__container > table > tbody > tr:nth-child(1) > td:nth-child(2)"
        )
    )

    grinex_task = asyncio.create_task(parser_service.get_grinex_usd_rate())

    tradingview_task = asyncio.create_task(
        parser_service.get_tradingview_usd(
            url="https://www.tradingview.com/symbols/XAUUSD/",
            selector="//span[contains(@class, 'last-JWoJqCpY js-symbol-last')]"
        )
    )

    def sync_abcex():
        return parser_service.get_abcex_rate(
            "https://abcex.io/api/v1/exchange/public/market-data/order-book/depth?marketId=USDTRUB&lang=ru"
        )
    loop = asyncio.get_running_loop()
    abcex_task = loop.run_in_executor(None, sync_abcex)

    def sync_cbr_usd():
        parser_service.update_usd_cbr_rates()
        cbr_t = parser_service.get_cbr_today_rate("USD")
        cbr_tm = parser_service.get_cbr_tomorrow_rate("USD")
        return (cbr_t, cbr_tm)
    cbr_task = loop.run_in_executor(None, sync_cbr_usd)

    tasks = {
        investing_task: "investing",
        profinance_task: "profinance",
        moex_task: "moex",
        grinex_task: "grinex",
        tradingview_task: "tradingview",
        abcex_task: "abcex",
        cbr_task: "cbr",
    }

    invest_rate = None
    profinance_rate = None
    moex_rate = None
    grinex_rate = None
    tradingview_rate = None
    abcex_rate = None
    cbr_today = None
    cbr_tomorrow = None

    pending = set(tasks.keys())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            source_name = tasks[d]
            try:
                result = d.result()
            except Exception as e:
                print(f"[{source_name}] Error: {e}")
                continue

            if source_name == "investing":
                invest_rate = result
            elif source_name == "profinance":
                profinance_rate = result
            elif source_name == "moex":
                moex_rate = result
            elif source_name == "grinex":
                grinex_rate = result
            elif source_name == "tradingview":
                tradingview_rate = result
            elif source_name == "abcex":
                abcex_rate = result
            elif source_name == "cbr":
                cbr_today, cbr_tomorrow = result

            # Обновим таблицу и сообщение
            table_text = build_currency_table(
                title="Курсы USD/RUB",
                investing=invest_rate,
                cbr_today=cbr_today,
                cbr_tomorrow=cbr_tomorrow,
                profinance=profinance_rate,
                moex=moex_rate,
                abcex=abcex_rate,
                grinex=grinex_rate,
                tranding_view=tradingview_rate
            )
            old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

            # Дополнительно: если получили Investing – отправим скриншот, если он есть
            if source_name == "investing" and invest_rate:
                try:
                    file_photo = FSInputFile(investing_updater.cached_usd_screenshot)
                    await message.answer_photo(file_photo, caption="Скриншот Investing (USD/RUB)")
                except Exception as e:
                    print(f"Не удалось отправить скриншот (USD): {e}")

    await parser_service.close_browser_context()
    set_process_state(message.from_user.id, False)
    await message.answer("Можете дальше отправлять команды.")


@router.message(Command("euro"))
async def cmd_euro(message: Message):
    """
    Аналогичный подход для EUR/RUB с параллельной загрузкой.
    """
    if get_process_state(message.from_user.id):
        await message.reply("У вас уже обрабатывается запрос.")
        return
    set_process_state(message.from_user.id, True)

    wait_msg = await message.answer("Начинаем сбор данных по EUR/RUB...")

    await parser_service.init_browser()
    await parser_service.init_browser_context(use_proxy=True)

    old_table_text = ""
    table_text = build_currency_table(
        title="Курсы EUR/RUB",
        investing=None,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None,
        abcex=None,    # "1 EUR -> X USD"
        grinex=None,   # "1 USD -> X EUR"
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # -- Параллельные задачи --
    async def get_investing_eur():
        return investing_updater.cached_eur_rate

    investing_task = asyncio.create_task(get_investing_eur())

    profinance_task = asyncio.create_task(
        parser_service.get_profinance_rate(
            url="https://www.profinance.ru/chart/eurrub/",
            selector="#b_30"
        )
    )

    moex_task = asyncio.create_task(
        parser_service.get_moex_rate(
            url="https://www.moex.com/ru/derivatives/currency-rate.aspx?currency=EUR_RUB",
            selector="#app > div:nth-child(2) > div.ui-container.-default > div > div.ui-table > div.ui-table__container > table > tbody > tr:nth-child(1) > td:nth-child(2)"
        )
    )

    # XE: "1 EUR -> X USD" и "1 USD -> X EUR"
    euro_to_usd_task = asyncio.create_task(parser_service.get_xe_rate_euro_dollar())
    usd_to_eur_task = asyncio.create_task(parser_service.get_xe_rate_dollar_euro())

    def sync_cbr_eur():
        parser_service.update_eur_cbr_rates()
        cbr_t = parser_service.get_cbr_today_rate("EUR")
        cbr_tm = parser_service.get_cbr_tomorrow_rate("EUR")
        return (cbr_t, cbr_tm)

    loop = asyncio.get_running_loop()
    cbr_task = loop.run_in_executor(None, sync_cbr_eur)

    tasks = {
        investing_task: "investing",
        profinance_task: "profinance",
        moex_task: "moex",
        euro_to_usd_task: "xe_euro_usd",
        usd_to_eur_task: "xe_usd_eur",
        cbr_task: "cbr",
    }

    invest_rate = None
    profinance_rate = None
    moex_rate = None
    xe_euro_usd = None
    xe_usd_eur = None
    cbr_today = None
    cbr_tomorrow = None

    pending = set(tasks.keys())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            source_name = tasks[d]
            try:
                result = d.result()
            except Exception as e:
                print(f"[{source_name}] Error: {e}")
                continue

            if source_name == "investing":
                invest_rate = result
            elif source_name == "profinance":
                profinance_rate = result
            elif source_name == "moex":
                moex_rate = result
            elif source_name == "xe_euro_usd":
                xe_euro_usd = result
            elif source_name == "xe_usd_eur":
                xe_usd_eur = result
            elif source_name == "cbr":
                cbr_today, cbr_tomorrow = result

            # Обновляем таблицу
            table_text = build_currency_table(
                title="Курсы EUR/RUB",
                investing=invest_rate,
                cbr_today=cbr_today,
                cbr_tomorrow=cbr_tomorrow,
                profinance=profinance_rate,
                moex=moex_rate,
                abcex=xe_euro_usd,    # "1 EUR -> X USD"
                grinex=xe_usd_eur,   # "1 USD -> X EUR"
                tranding_view=None
            )
            old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

            # Отправим скриншот Investing, если нужно
            if source_name == "investing" and invest_rate:
                try:
                    file_photo = FSInputFile(investing_updater.cached_eur_screenshot)
                    await message.answer_photo(file_photo, caption="Скриншот Investing (EUR/RUB)")
                except Exception as e:
                    print(f"Не удалось отправить скриншот (EUR): {e}")

    await parser_service.close_browser_context()
    set_process_state(message.from_user.id, False)
    await message.answer("Можете дальше отправлять команды.")


@router.message(Command("cny"))
async def cmd_cny(message: Message):
    """
    Параллельная загрузка для CNY/RUB, с динамическим обновлением.
    """
    if get_process_state(message.from_user.id):
        await message.reply("У вас уже обрабатывается запрос.")
        return
    set_process_state(message.from_user.id, True)

    wait_msg = await message.answer("Начинаем сбор данных по CNY/RUB...")

    await parser_service.init_browser()
    await parser_service.init_browser_context(use_proxy=True)

    old_table_text = ""
    table_text = build_currency_table(
        title="Курсы CNY/RUB",
        investing=None,
        cbr_today=None,
        cbr_tomorrow=None,
        profinance=None,
        moex=None,
        abcex=None,   # "1 USD -> X CNY"
        grinex=None,  # "1 CNY -> X USD"
        tranding_view=None
    )
    old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

    # -- Параллельные задачи --
    async def get_investing_cny():
        return investing_updater.cached_cny_rate

    investing_task = asyncio.create_task(get_investing_cny())

    profinance_task = asyncio.create_task(
        parser_service.get_profinance_rate(
            url="https://www.profinance.ru/chart/cnyrub/",
            selector="#b_CNY_RUB"
        )
    )

    moex_task = asyncio.create_task(
        parser_service.get_moex_rate(
            url="https://www.moex.com/ru/derivatives/currency-rate.aspx?currency=CNY_RUB",
            selector="#app > div:nth-child(2) > div.ui-container.-default > div > div.ui-table > div.ui-table__container > table > tbody > tr:nth-child(1) > td:nth-child(2)"
        )
    )

    # XE: "1 USD -> X CNY" и "1 CNY -> X USD"
    usd_cny_task = asyncio.create_task(parser_service.get_xe_rate_usd_yuan())
    cny_usd_task = asyncio.create_task(parser_service.get_xe_rate_yuan_usd())

    def sync_cbr_cny():
        parser_service.update_cny_cbr_rates()
        cbr_t = parser_service.get_cbr_today_rate("CNY")
        cbr_tm = parser_service.get_cbr_tomorrow_rate("CNY")
        return (cbr_t, cbr_tm)

    loop = asyncio.get_running_loop()
    cbr_task = loop.run_in_executor(None, sync_cbr_cny)

    tasks = {
        investing_task: "investing",
        profinance_task: "profinance",
        moex_task: "moex",
        usd_cny_task: "xe_usd_cny",
        cny_usd_task: "xe_cny_usd",
        cbr_task: "cbr",
    }

    invest_rate = None
    profinance_rate = None
    moex_rate = None
    xe_usd_cny = None
    xe_cny_usd = None
    cbr_today = None
    cbr_tomorrow = None

    pending = set(tasks.keys())
    while pending:
        done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
        for d in done:
            source_name = tasks[d]
            try:
                result = d.result()
            except Exception as e:
                print(f"[{source_name}] Error: {e}")
                continue

            if source_name == "investing":
                invest_rate = result
            elif source_name == "profinance":
                profinance_rate = result
            elif source_name == "moex":
                moex_rate = result
            elif source_name == "xe_usd_cny":
                xe_usd_cny = result
            elif source_name == "xe_cny_usd":
                xe_cny_usd = result
            elif source_name == "cbr":
                cbr_today, cbr_tomorrow = result

            # Обновляем таблицу
            table_text = build_currency_table(
                title="Курсы CNY/RUB",
                investing=invest_rate,
                cbr_today=cbr_today,
                cbr_tomorrow=cbr_tomorrow,
                profinance=profinance_rate,
                moex=moex_rate,
                abcex=xe_usd_cny,   # "1 USD -> X CNY"
                grinex=xe_cny_usd, # "1 CNY -> X USD"
                tranding_view=None
            )
            old_table_text = await edit_message_if_changed(wait_msg, table_text, old_table_text)

            # Если Investing готов — отправим скриншот
            if source_name == "investing" and invest_rate:
                try:
                    file_photo = FSInputFile(investing_updater.cached_cny_screenshot)
                    await message.answer_photo(file_photo, caption="Скриншот Investing (CNY/RUB)")
                except Exception as e:
                    print(f"Не удалось отправить скриншот (CNY): {e}")

    await parser_service.close_browser_context()
    set_process_state(message.from_user.id, False)
    await message.answer("Можете дальше отправлять команды.")
