import logging
import asyncio

async def log_start():
    """
    Демонстрационная функция, вызываемая при старте, если DEBUG_MODE=True.
    Можно вывести любые отладочные сообщения.
    """
    await asyncio.sleep(0.1)  # имитируем асинхронное действие
    logging.debug("log_start(): Бот запущен в режиме отладки. Дополнительные логи включены.")
