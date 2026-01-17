import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from atp.config_init import initialize_config

# Инициализируем конфигурацию при импорте модуля
DOCKER = os.getenv("DOCKER", "0") == "1"
config_dir = initialize_config()
settings_file = config_dir / "settings.conf"
docker_settings_file = config_dir / "settings-docker.conf"

# Загружаем настройки из settings.conf
if settings_file.exists():
    load_dotenv(settings_file)
else:
    # Fallback: загружаем из .env для обратной совместимости
    load_dotenv()

if DOCKER and docker_settings_file.exists():
    load_dotenv(docker_settings_file, override=True)


# Настройки импорта видео
IMPORT_LIKED_VIDEOS: bool = os.getenv("IMPORT_LIKED_VIDEOS", "true").lower() == "true"
IMPORT_FAVORITE_VIDEOS: bool = os.getenv("IMPORT_FAVORITE_VIDEOS", "true").lower() == "true"

# Настройки тиктока
DOWNLOAD_FROM_TIKTOK: bool = os.getenv("DOWNLOAD_FROM_TIKTOK", "true").lower() == "true"
TIKTOK_USER: str = os.getenv("TIKTOK_USER", "")

# Настройки Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# Настройки проверки доступности
CHECK_INTERVAL_DAYS: int = int(os.getenv("CHECK_INTERVAL_DAYS", "7"))

# Пытаться скачать failed видео, вдруг их восстановили
HOPE_MODE: bool = os.getenv("HOPE_MODE", "false").lower() == "true"

# Количество попыток при скачивании/проверке видео
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))

# Пытаться обойти анти-бот защиту тиктока
ANTI_BOT_BYPASS: bool = os.getenv("ANTI_BOT_BYPASS", "false").lower() == "true"

# Настройки папок и базы
DATABASE_FILE = os.getenv("DATABASE", "tiktok_videos.db")
if not os.path.isabs(DATABASE_FILE):
    DATABASE_FILE = str(config_dir / DATABASE_FILE)
DATABASE_URL: str = f"sqlite:///{DATABASE_FILE}"

DOWNLOADS_DIR: str = os.getenv("DOWNLOADS_DIR", "/downloads")

TIKTOK_DATA_FILE: str = os.getenv("TIKTOK_DATA_FILE", "user_data_tiktok.json")
if not os.path.isabs(TIKTOK_DATA_FILE):
    TIKTOK_DATA_FILE = str(config_dir / TIKTOK_DATA_FILE)

# Файл с cookies в формате Netscape для yt-dlp
COOKIES_FILE: str | None = os.getenv("COOKIES_FILE", "cookies.txt")
if not os.path.isabs(COOKIES_FILE):
    COOKIES_FILE = str(config_dir / COOKIES_FILE)
    if not os.path.exists(COOKIES_FILE):
        COOKIES_FILE = None

TMP_DIR: Path = Path(tempfile.gettempdir()) / "gallery_dl"
