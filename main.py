# main.py
import asyncio
from services.parser_service import ParserService
from aiogram import Bot, Dispatcher
from aiogram.client.bot import DefaultBotProperties
from utils.config import config
from utils.logging_config import setup_logging
from logs.log_info import log_start
from db.database import init_db, reset_all_process_states
from db.requests_database import init_requests_db
from handlers.user_handlers import router as user_router
from handlers.currency_handlers import router as currency_router
from handlers.solve_handlers import router as solve_router
from handlers.stats_handlers import router as stats_router

# Вместо from main import investing_updater -> импортируем из updater_instance
from services.updater_instance import investing_updater

logger = setup_logging()

async def main():
    logger.info("Инициализация БД...")
    init_db()
    reset_all_process_states()
    init_requests_db()

    parser_service = ParserService()

    if config.DEBUG_MODE:
        await log_start()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    # Регистрируем все роутеры
    dp.include_router(user_router)
    dp.include_router(currency_router)
    dp.include_router(solve_router)
    dp.include_router(stats_router)

    # Запускаем фоновую задачу
    logger.info("Запуск обновления Investing...")
    asyncio.create_task(investing_updater.start_updating(interval_seconds=30))

    # Очищаем старый webhook, если был
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        logger.info("Бот запущен. Стартуем long polling...")
        await dp.start_polling(bot)
    except Exception as ex:
        logger.error(f"Ошибка при работе бота: {ex}", exc_info=True)
    finally:
        logger.info("Остановка бота. Закрываем сессию...")
        await bot.session.close()
        await investing_updater.stop()

if __name__ == "__main__":
    try:
        logger.info("Запуск main()...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Бот остановлен вручную (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Фатальная ошибка при запуске бота: {e}", exc_info=True)
