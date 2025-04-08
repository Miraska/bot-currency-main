import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DEBUG_MODE: bool = os.getenv("DEBUG_MODE", "False").lower() == "true"
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    LOG_FILE: str = "logs/bot.log"

    # Прокси (пример, если нужно несколько)
    PROXY_HOST_1: str = os.getenv("PROXY_HOST_1", "")
    PROXY_PORT_1: str = os.getenv("PROXY_PORT_1", "")
    PROXY_USERNAME_1: str = os.getenv("PROXY_USERNAME_1", "")
    PROXY_PASSWORD_1: str = os.getenv("PROXY_PASSWORD_1", "")

    PROXY_HOST_2: str = os.getenv("PROXY_HOST_2", "")
    PROXY_PORT_2: str = os.getenv("PROXY_PORT_2", "")
    PROXY_USERNAME_2: str = os.getenv("PROXY_USERNAME_2", "")
    PROXY_PASSWORD_2: str = os.getenv("PROXY_PASSWORD_2", "")

    PROXY_HOST_3: str = os.getenv("PROXY_HOST_3", "")
    PROXY_PORT_3: str = os.getenv("PROXY_PORT_3", "")
    PROXY_USERNAME_3: str = os.getenv("PROXY_USERNAME_3", "")
    PROXY_PASSWORD_3: str = os.getenv("PROXY_PASSWORD_3", "")

config = Config()
