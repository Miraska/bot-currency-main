import asyncio
import datetime
import traceback
from playwright.async_api import async_playwright, Page
from typing import Optional

class InvestingUpdater:
    """
    Класс для фоновой задачи: каждые N секунд обновляет курсы по USD/RUB, EUR/RUB, CNY/RUB
    с сайта Investing, используя браузер и три вкладки (Page).
    Теперь браузер перезапускается каждые 60 минут, чтобы избежать проблем с кешем или зависанием.
    В случае ошибки инициализации или обновления происходит повторный запуск.
    """

    def __init__(self):
        self.count_restart = 0
        self.running = False
        self.browser = None
        self.context = None

        # Страницы под каждую валюту
        self.page_usd: Optional[Page] = None
        self.page_eur: Optional[Page] = None
        self.page_cny: Optional[Page] = None

        # Сохранённые данные (в тексте) и скриншоты (пути к файлам)
        self.cached_usd_rate: Optional[str] = None
        self.cached_eur_rate: Optional[str] = None
        self.cached_cny_rate: Optional[str] = None

        self.cached_usd_screenshot: str = "logs/screenshots/screenshot_investing_usd.png"
        self.cached_eur_screenshot: str = "logs/screenshots/screenshot_investing_eur.png"
        self.cached_cny_screenshot: str = "logs/screenshots/screenshot_investing_cny.png"

    async def start_updating(self, interval_seconds: int = 30):
        """
        Запускает вечный цикл, в котором каждые 60 минут происходит перезапуск браузера.
        Если произошла ошибка инициализации или обновления, происходит повторный запуск.
        """
        self.running = True
        restart_interval_seconds = 60 * 60  # Перезапуск каждые 60 минут

        async with async_playwright() as p:
            while self.running:
                try:
                    # Создаем новый браузер и контекст
                    self.browser = await p.chromium.launch(
                        headless=False,
                        args=["--disable-blink-features=AutomationControlled"]
                    )
                    self.context = await self.browser.new_context()

                    # Создаем страницы для каждой валюты
                    self.page_usd = await self.context.new_page()
                    self.page_eur = await self.context.new_page()
                    self.page_cny = await self.context.new_page()

                    # Переходим на стартовые URL с проверкой ошибок
                    await self.page_usd.goto("https://ru.investing.com/currencies/usd-rub", wait_until="domcontentloaded")
                    await self.page_eur.goto("https://ru.investing.com/currencies/eur-rub", wait_until="domcontentloaded")
                    await self.page_cny.goto("https://ru.investing.com/currencies/cny-rub", wait_until="domcontentloaded")

                    # Закрываем cookie-баннер на каждой странице
                    await self._close_cookie_banner(self.page_usd)
                    await self._close_cookie_banner(self.page_eur)
                    await self._close_cookie_banner(self.page_cny)

                    # Скроллим страницы для корректного отображения данных
                    await self.page_usd.evaluate("window.scrollTo(0, 300)")
                    await self.page_eur.evaluate("window.scrollTo(0, 300)")
                    await self.page_cny.evaluate("window.scrollTo(0, 300)")
                except Exception as init_error:
                    print("Ошибка при инициализации браузера или страниц:", init_error)
                    traceback.print_exc()
                    await self._close_all()
                    # Подождать немного перед повторным запуском
                    await asyncio.sleep(5)
                    continue  # Перезапускаем цикл

                # Фиксируем время запуска текущей сессии браузера
                session_start = datetime.datetime.now()

                # Внутренний цикл: обновление курсов с периодичностью interval_seconds
                while self.running and ((datetime.datetime.now() - session_start).total_seconds() < restart_interval_seconds):
                    await asyncio.sleep(interval_seconds)

                    try:
                        # Обновляем USD
                        await self._update_currency(
                            page=self.page_usd,
                            selector='span[data-test="instrument-price-last"]',
                            screenshot_path=self.cached_usd_screenshot,
                            set_rate_callback=lambda val: setattr(self, "cached_usd_rate", val)
                        )
                        # Обновляем EUR
                        await self._update_currency(
                            page=self.page_eur,
                            selector='span[data-test="instrument-price-last"]',
                            screenshot_path=self.cached_eur_screenshot,
                            set_rate_callback=lambda val: setattr(self, "cached_eur_rate", val)
                        )
                        # Обновляем CNY
                        await self._update_currency(
                            page=self.page_cny,
                            selector='span[data-test="instrument-price-last"]',
                            screenshot_path=self.cached_cny_screenshot,
                            set_rate_callback=lambda val: setattr(self, "cached_cny_rate", val)
                        )
                    except Exception as update_error:
                        print("Ошибка при обновлении курса:", update_error)
                        traceback.print_exc()
                        # При ошибке обновления прерываем внутренний цикл и перезапускаем браузер
                        break

                # Закрываем текущие страницы, контекст и браузер перед перезапуском
                await self._close_all()

    async def _update_currency(self, page: Page, selector: str, screenshot_path: str, set_rate_callback):
        """
        Обновляет курс для конкретной вкладки:
        - получает текст по селектору,
        - делает скриншот,
        - сохраняет данные через колбэк.
        """
        # Получаем текст селектора
        rate_text: str = await page.locator(selector).text_content()

        # Делаем скриншот всей страницы
        await page.screenshot(path=screenshot_path)

        # Сохраняем курс, если он получен
        if rate_text:
            set_rate_callback(rate_text.strip())

    async def _close_cookie_banner(self, page: Page):
        """
        Закрывает cookie-баннер на странице Investing, если он видим.
        """
        try:
            if await page.is_visible("#onetrust-accept-btn-handler", timeout=2000):
                await page.click("#onetrust-accept-btn-handler")
        except Exception:
            pass

    async def _close_all(self):
        """
        Закрывает все открытые страницы, контекст и браузер.
        """
        for resource in [self.page_usd, self.page_eur, self.page_cny]:
            try:
                if resource:
                    await resource.close()
            except Exception:
                pass
        try:
            if self.context:
                await self.context.close()
        except Exception:
            pass
        try:
            if self.browser:
                await self.browser.close()
        except Exception:
            pass

        finally:
            self.count_restart += 1
            print("Count of restarting: " + str(self.count_restart))
