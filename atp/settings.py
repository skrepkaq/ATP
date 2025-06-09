import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

# Пути к файлам и директориям
DATABASE_URL: str = f"sqlite:///{os.getenv('DATABASE', 'tiktok_videos.db')}"
DOWNLOADS_DIR: str = os.getenv("DOWNLOADS_DIR", "./downloads")
TIKTOK_DATA_FILE: str = os.getenv("TIKTOK_DATA_FILE", "./user_data_tiktok.json")

# Настройки Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# Настройки тиктока
DOWNLOAD_FROM_TIKTOK: bool = os.getenv("DOWNLOAD_FROM_TIKTOK", "true").lower() == "true"
TIKTOK_USER: str = os.getenv("TIKTOK_USER", "")

# Настройки browserless
BROWSERLESS_URL: str = os.getenv("BROWSERLESS_URL", "ws://localhost:3000")

# Настройки проверки доступности
CHECK_INTERVAL_DAYS: int = int(os.getenv("CHECK_INTERVAL_DAYS", "7"))


# Настройки импорта видео
IMPORT_LIKED_VIDEOS: bool = os.getenv("IMPORT_LIKED_VIDEOS", "true").lower() == "true"
IMPORT_FAVORITE_VIDEOS: bool = os.getenv("IMPORT_FAVORITE_VIDEOS", "true").lower() == "true"

# Настройки временных директорий
TMP_DIR: str = os.path.join(tempfile.gettempdir(), "gallery_dl")

# Настройки для retry логики
MAX_RETRIES: int = 3
