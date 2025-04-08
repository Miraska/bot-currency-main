import random
import datetime
import requests
import re
import xml.etree.ElementTree as ET
import asyncio
import traceback

from typing import Optional, Dict, Tuple
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from utils.config import config

class ParserService:
    """
    Сервис, объединяющий логику парсинга курсов для USD, EUR, CNY:
      - CBR (с «сегодня/завтра» и fallback на последний известный курс)
      - Investing (скриншоты + извлечение курса)
      - ProFinance (с поддержкой прокси)
      - MOEX
      - Grinex (новый источник для USD, USDT/RUB)
      - TradingView
      - XE
      и т.д.
    """

    def __init__(self) -> None:
        """
        Для каждой валюты храним:
          - today_rate: курс на сегодня (если дата в XML совпадает с текущей)
          - tomorrow_rate: курс на завтра (если уже опубликован)
          - last_cbr_rate: последний доступный курс (на случай, если «сегодня» нет в XML)
        """
        self.usd_cbr_data = {"today_rate": None, "tomorrow_rate": None, "last_cbr_rate": None}
        self.eur_cbr_data = {"today_rate": None, "tomorrow_rate": None, "last_cbr_rate": None}
        self.cny_cbr_data = {"today_rate": None, "tomorrow_rate": None, "last_cbr_rate": None}

        # Список прокси, если нужны
        self.proxies = [
            {
                "server": f"http://{config.PROXY_HOST_1}:{config.PROXY_PORT_1}",
                "username": config.PROXY_USERNAME_1,
                "password": config.PROXY_PASSWORD_1,
            },
            {
                "server": f"http://{config.PROXY_HOST_2}:{config.PROXY_PORT_2}",
                "username": config.PROXY_USERNAME_2,
                "password": config.PROXY_PASSWORD_2,
            },
            {
                "server": f"http://{config.PROXY_HOST_3}:{config.PROXY_PORT_3}",
                "username": config.PROXY_USERNAME_3,
                "password": config.PROXY_PASSWORD_3,
            }
        ]

        # Переменные для общего Playwright-браузера (если нужно хранить в едином экземпляре).
        # Но можно открывать/закрывать их в каждом запросе – зависит от задачи.
        self.playwright = None
        self.browser: Optional[Browser] = None

    # --------------------------------------------------------------------
    # 1. Методы для инициализации / завершения работы с общим браузером
    # --------------------------------------------------------------------
    async def init_browser(self):
        """
        Запускаем Playwright и Chromium-браузер один раз для всего ParserService.
        Если уже запущено, повторно не создаём.
        """
        if self.playwright is None:
            self.playwright = await async_playwright().start()

        if self.browser is None:
            self.browser = await self.playwright.chromium.launch(headless=True)

    async def close_browser(self):
        """
        Если нужно руками закрыть браузер и остановить Playwright.
        """
        if self.browser is not None:
            await self.browser.close()
            self.browser = None
        if self.playwright is not None:
            await self.playwright.stop()
            self.playwright = None

    # ------------------------------------------------------
    # 2. Логика CBR (сегодня / завтра, fallback)
    # ------------------------------------------------------
    def update_cbr_rates_for(self, char_code: str) -> None:
        """
        Обновляет для выбранной валюты (USD/EUR/CNY) today_rate, tomorrow_rate и last_cbr_rate.
        Принцип:
          - Если в XML есть курс на сегодня, пишем в today_rate + last_cbr_rate
          - Если не совпадает — today_rate=None, last_cbr_rate = (что бы ни пришло)
          - Пробуем получить курс на завтра; если нет — tomorrow_rate=None
        """
        currency_data = self._get_cbr_data_dict(char_code)
        if not currency_data:
            return

        today = datetime.date.today()
        xml_date_today, rate_today = self._get_cbr_xml_rate(char_code, date=today)

        if rate_today:
            currency_data["last_cbr_rate"] = rate_today
            if xml_date_today == today:
                currency_data["today_rate"] = rate_today
            else:
                currency_data["today_rate"] = None
        else:
            currency_data["today_rate"] = None

        tomorrow = today + datetime.timedelta(days=1)
        xml_date_tomorrow, rate_tomorrow = self._get_cbr_xml_rate(char_code, date=tomorrow)
        if rate_tomorrow and xml_date_tomorrow == tomorrow:
            currency_data["tomorrow_rate"] = rate_tomorrow
        else:
            currency_data["tomorrow_rate"] = None

    def get_cbr_today_rate(self, char_code: str) -> Optional[str]:
        """
        Возвращает курс на сегодня, если есть; иначе — fallback на last_cbr_rate.
        """
        currency_data = self._get_cbr_data_dict(char_code)
        if not currency_data:
            return None
        if currency_data["today_rate"] is not None:
            return currency_data["today_rate"]
        elif currency_data["last_cbr_rate"] is not None:
            return currency_data["last_cbr_rate"]
        else:
            return None

    def get_cbr_tomorrow_rate(self, char_code: str) -> Optional[str]:
        """
        Возвращает курс на завтра, если есть. Иначе None.
        """
        currency_data = self._get_cbr_data_dict(char_code)
        if not currency_data:
            return None
        return currency_data["tomorrow_rate"]

    def _get_cbr_data_dict(self, char_code: str) -> Optional[Dict[str, Optional[str]]]:
        """
        Вспомогательный метод, возвращающий ссылку на словарь CBR-данных
        для выбранного CharCode ('USD', 'EUR', 'CNY').
        """
        if char_code.upper() == "USD":
            return self.usd_cbr_data
        elif char_code.upper() == "EUR":
            return self.eur_cbr_data
        elif char_code.upper() == "CNY":
            return self.cny_cbr_data
        else:
            return None

    def _get_cbr_xml_rate(
            self,
            char_code: str,
            date: Optional[datetime.date] = None
    ) -> Tuple[Optional[datetime.date], Optional[str]]:
        """
        Запрашивает XML ЦБ (https://www.cbr.ru/scripts/XML_daily.asp).
        Если date=None, берём сегодняшний.
        Возвращает (xml_date, rate_str), где rate_str, например, '75,32'.
        Если не найден — (None, None).
        """
        try:
            if date:
                date_str = date.strftime("%d/%m/%Y")
                url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date_str}"
            else:
                url = "https://www.cbr.ru/scripts/XML_daily.asp"

            resp = requests.get(url)
            resp.raise_for_status()
            root = ET.fromstring(resp.content)

            xml_date_str = root.attrib.get("Date", None)
            xml_date = None
            if xml_date_str:
                try:
                    xml_date = datetime.datetime.strptime(xml_date_str, "%d.%m.%Y").date()
                except:
                    pass

            val_str = None
            for valute in root.findall("Valute"):
                if valute.find("CharCode").text == char_code.upper():
                    val_str = valute.find("Value").text
                    break

            return (xml_date, val_str)
        except Exception as e:
            print(f"Ошибка при запросе CBR ({char_code}): {e}")
            return (None, None)

    # ------------------------------------------------------
    # 3. MOEX
    # ------------------------------------------------------
    async def get_moex_rate(self, url: str, selector: str) -> Optional[str]:
        """
        Простой метод для получения курса с MOEX, используя новый контекст.
        """
        try:
            await self.init_browser()
            context = await self.browser.new_context()
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector(selector, timeout=15000)
            moex_rate = await page.locator(selector).text_content()

            await context.close()
            return moex_rate
        except Exception as e:
            print(f"[get_moex_rate] Error: {e}")
            return None

    # ------------------------------------------------------
    # 4. PROFINANCE (с прокси)
    # ------------------------------------------------------
    async def get_profinance_rate(self, url: str, selector: str) -> Optional[str]:
        """
        Получение курса с ProFinance, используя случайный прокси в отдельном контексте.
        """
        try:
            await self.init_browser()
            chosen_proxy = random.choice(self.proxies)
            context = await self.browser.new_context(proxy=chosen_proxy)
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)  # Ждем для подгрузки динамического контента
            await page.wait_for_selector(selector, state="visible", timeout=15000)

            rate_text = await page.locator(selector).text_content()

            await context.close()
            return rate_text
        except Exception as e:
            print(f"[get_profinance_rate] Error: {e}")
            return None

    # ------------------------------------------------------
    # 5. ABCEX (используется только для USD) — requests
    # ------------------------------------------------------
    def get_abcex_rate(self, url: str) -> Optional[str]:
        """
        Получаем курс (первый bid price) с ABCEX в формате JSON.
        Пример URL:
          "https://abcex.io/api/v1/exchange/public/market-data/order-book/depth?marketId=USDTRUB&lang=ru"
        """
        try:
            resp = requests.get(url)
            resp.raise_for_status()
            data = resp.json()
            if "bid" in data and data["bid"]:
                return str(data["bid"][0]["price"])
            return None
        except Exception as e:
            print(f"[get_abcex_rate] Ошибка: {e}")
            return None

    # ------------------------------------------------------
    # 6. GARANTEX (requests), просто оставляем
    # ------------------------------------------------------
    def get_garantex_rate(self, market: str) -> Optional[str]:
        try:
            url = f"https://garantex.org/api/v2/depth?market={market}"
            resp = requests.get(url)
            resp.raise_for_status()
            data = resp.json()

            if "bids" in data and data["bids"]:
                return str(data["bids"][0]["price"])
            return None
        except Exception as e:
            print(f"[get_garantex_rate] Error: {e}")
            return None

    # ------------------------------------------------------
    # 7. TRADING-VIEW
    # ------------------------------------------------------
    async def get_tradingview_usd(self, url: str, selector: str) -> Optional[str]:
        """
        Парсим TradingView, используя новый контекст и случайный прокси.
        """
        try:
            await self.init_browser()
            chosen_proxy = random.choice(self.proxies)
            context = await self.browser.new_context(proxy=chosen_proxy)
            page = await context.new_page()

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_selector(selector, state="visible", timeout=15000)

            rate_text = await page.locator(selector).text_content()

            await context.close()
            return rate_text
        except Exception as e:
            print(f"[get_tradingview_usd] Error: {e}")
            return None

    # ------------------------------------------------------
    # 8. Парсеры XE (EUR, CNY) — используем общий браузер с отдельным контекстом
    # ------------------------------------------------------
    async def get_xe_rate_euro_dollar(self) -> Optional[str]:
        """
        "1 EUR = X USD"
        """
        url = 'https://www.xe.com/currencyconverter/convert/?Amount=1&From=EUR&To=USD'
        xpath_selector = '//*[@id="__next"]/div/div[5]/div[2]/div[1]/div[1]/div/div[2]/div[3]/div/div[1]/div[1]/p[2]'
        return await self.fetch_rate(url, xpath_selector, is_xpath=True)

    async def get_xe_rate_dollar_euro(self) -> Optional[str]:
        """
        "1 USD = X EUR"
        """
        url = 'https://www.xe.com/currencyconverter/convert/?Amount=1&From=USD&To=EUR'
        xpath_selector = '//*[@id="__next"]/div/div[5]/div[2]/div[1]/div[1]/div/div[2]/div[3]/div/div[1]/div[1]/p[2]'
        return await self.fetch_rate(url, xpath_selector, is_xpath=True)

    async def get_xe_rate_yuan_usd(self) -> Optional[str]:
        """
        "1 CNY = X USD"
        """
        url = 'https://www.xe.com/currencyconverter/convert/?Amount=1&From=CNY&To=USD'
        xpath_selector = '//*[@id="__next"]/div/div[5]/div[2]/div[1]/div[1]/div/div[2]/div[3]/div/div[1]/div[1]/p[2]'
        return await self.fetch_rate(url, xpath_selector, is_xpath=True)

    async def get_xe_rate_usd_yuan(self) -> Optional[str]:
        """
        "1 USD = X CNY"
        """
        url = 'https://www.xe.com/currencyconverter/convert/?Amount=1&From=USD&To=CNY'
        xpath_selector = '//*[@id="__next"]/div/div[5]/div[2]/div[1]/div[1]/div/div[2]/div[3]/div/div[1]/div[1]/p[2]'
        return await self.fetch_rate(url, xpath_selector, is_xpath=True)

    # ------------------------------------------------------
    # 9. Grinex (USD USDT/RUB)
    # ------------------------------------------------------
    async def get_grinex_usd_rate(self) -> Optional[str]:
        """
        Получает курс с сайта Grinex для USD (USDT/RUB).
        Перед получением курса производится клик по ссылке "#usdta7a5_tab" для переключения вкладки.
        Если появляется модальное окно (с id "privacy-agree-modal"), пытаемся его закрыть:
          - Если есть кнопка закрытия, кликаем по ней;
          - Иначе нажимаем Escape.
        Затем ждём появления нужного элемента (до 30 секунд) и извлекаем текст.
        """
        selector = "#order_book_holder > div:nth-child(2) > div.bid_orders_panel > table > tbody > tr:nth-child(1) > td.price.col-xs-8.overflow-aut > div"
        try:
            await self.init_browser()
            chosen_proxy = random.choice(self.proxies)
            context = await self.browser.new_context(proxy=chosen_proxy)
            page = await context.new_page()
            url = "https://grinex.io/trading/usdta7a5"

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)  # Доп. ожидание загрузки контента

            # Если появляется модальное окно, пытаемся его закрыть
            try:
                if await page.locator("#privacy-agree-modal").is_visible(timeout=5000):
                    close_btn = page.locator("#privacy-agree-modal button[data-action='click->dialog#closeOutside']")
                    if await close_btn.count() > 0:
                        await close_btn.first.click(timeout=5000)
                    else:
                        await page.keyboard.press("Escape")
                    await page.wait_for_selector("#privacy-agree-modal", state="hidden", timeout=5000)
            except Exception as e:
                print(f"Ошибка при закрытии модального окна: {e}")

            await page.click("#usdta7a5_tab", timeout=30000)
            await page.wait_for_timeout(3000)

            # Второй элемент
            element = page.locator(selector).nth(1)
            total_wait = 0
            interval = 500
            max_wait = 30000
            while total_wait < max_wait:
                if await element.is_visible():
                    break
                await page.wait_for_timeout(interval)
                total_wait += interval

            if total_wait >= max_wait:
                raise Exception("Элемент не стал видимым за 30 секунд")

            text = await element.text_content()
            await context.close()

            value = re.sub(r'[^0-9.,]', '', text).replace(',', '.')
            return value
        except Exception as e:
            print(f"[get_grinex_usd_rate] Error: {e}")
            return None

    # ------------------------------------------------------
    # 10. Методы обновления курсов CBR в упрощённом варианте
    # ------------------------------------------------------
    def update_usd_cbr_rates(self) -> None:
        self.update_cbr_rates_for("USD")

    def update_eur_cbr_rates(self) -> None:
        self.update_cbr_rates_for("EUR")

    def update_cny_cbr_rates(self) -> None:
        self.update_cbr_rates_for("CNY")

    # ------------------------------------------------------
    # 11. Универсальная fetch_rate (для XE и т.п.)
    # ------------------------------------------------------
    async def fetch_rate(self, url, selector, is_xpath=False) -> Optional[str]:
        """
        Переход на страницу url, ожидание по селектору (CSS или XPath) и извлечение inner_text().
        Берём случайный прокси для каждого запроса. Три попытки (повторяем при ошибках).
        """
        for attempt in range(3):
            try:
                await self.init_browser()
                chosen_proxy = random.choice(self.proxies)
                context = await self.browser.new_context(proxy=chosen_proxy)
                page = await context.new_page()

                await page.goto(url)
                await page.wait_for_timeout(5000)

                if is_xpath:
                    await page.wait_for_selector(f"xpath={selector}", timeout=10000)
                    rate_element = await page.query_selector(f"xpath={selector}")
                else:
                    await page.wait_for_selector(selector, timeout=10000)
                    rate_element = await page.query_selector(selector)

                if rate_element:
                    rate_text = await rate_element.inner_text()
                    rate_clean = re.sub(r'[^0-9.,]', '', rate_text).replace(',', '.')
                    await context.close()
                    return rate_clean
                else:
                    print(f"Курс не найден по селектору: {selector}")
                    await context.close()
                    return None

            except Exception as e:
                print(f"Ошибка при получении курса (попытка {attempt + 1}/3): {str(e)}")
                await asyncio.sleep(2)

        return None
