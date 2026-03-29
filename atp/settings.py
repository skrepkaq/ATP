import logging
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DOCKER = os.getenv("DOCKER", "0") == "1"


def _get_project_root() -> Path:
    """Определяет корень проекта.

    Корень проекта - это директория, содержащая compose.yaml и atp/
    (на три уровня выше от atp/settings.py).

    :return: Путь к корню проекта
    """
    return Path(__file__).parent.parent


def get_config_dir() -> Path:
    """Определяет путь к директории конфигурации.

    Проверяет наличие /config, если существует - использует его
    (случай когда volume смонтирован в Docker).
    Иначе использует config/ относительно корня проекта.

    :return: Путь к директории конфигурации
    """
    if custom_config_dir := os.getenv("TEST_CONFIG_DIR"):
        return Path(custom_config_dir)
    if DOCKER:
        return Path("/config")
    return _get_project_root() / "config"


def load_config() -> Path:
    """Инициализирует директорию конфигурации.

    Создаёт директорию config, если её нет, и копирует
    example.settings.conf в settings.conf, если settings.conf не существует.

    :return: Путь к директории конфигурации
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    settings_path = config_dir / "settings.conf"
    example_path = _get_project_root() / "example.settings.conf"
    if not settings_path.exists() and example_path.exists():
        shutil.copy2(example_path, settings_path)
        print(
            f"Created {settings_path} from example. "
            "Please configure it before use and restart the application."
        )  # для обратной совместимости, оставляем print вместо logger.info
        while True:
            time.sleep(1)

    upgrade_config()

    settings_file = config_dir / "settings.conf"

    # Загружаем настройки из settings.conf
    if settings_file.exists():
        load_dotenv(settings_file)
    else:
        # Fallback: загружаем из .env для обратной совместимости
        load_dotenv()
    return config_dir


def set_config_value(key: str, value: str) -> None:
    """Устанавливает значение в settings.conf.

    :param key: Ключ
    :param value: Значение
    """
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"
    with open(settings_file, "r+") as f:
        config = f.readlines()
        for i, line in enumerate(config):
            if line.startswith(key):
                config[i] = f"{key}={value}\n"
                break
        f.seek(0)
        f.writelines(config)
        f.truncate()


def get_config_version() -> int:
    """Получает версию конфигурации из settings.conf."""
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"
    with open(settings_file) as f:
        config = f.read()
        return int(re.search(r"CONFIG_VERSION=(\d+)", config).group(1))


def version_2() -> None:
    """Обновляет конфигурацию до версии 2."""
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"
    with open(settings_file, "a") as f:
        f.write(
            "\n# Пытаться скачать failed видео, вдруг их восстановили. "
            "Советую поставить MAX_RETRIES=1"
            "\nHOPE_MODE=false"
            "\nMAX_RETRIES=3\n"
        )


def version_3() -> None:
    """Обновляет конфигурацию до версии 3."""
    config_dir = get_config_dir()
    REMOVE_LINES = [
        "# Настройки browserless",
        "BROWSERLESS_URL",
    ]
    for settings_file in ["settings-docker.conf", "settings.conf"]:
        settings_path = config_dir / settings_file
        if settings_path.exists():
            with open(settings_path, "r+") as f:
                config = f.readlines()
                for remove_line in REMOVE_LINES:
                    config = [line for line in config if not line.startswith(remove_line)]
                f.seek(0)
                f.writelines(config)
                f.truncate()


def version_4() -> None:
    """Обновляет конфигурацию до версии 4."""
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"
    with open(settings_file, "a") as f:
        f.write("\n# Пытаться обойти анти-бот защиту тиктока\nANTI_BOT_BYPASS=false\n")


def version_5() -> None:
    """Обновляет конфигурацию до версии 5."""
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"
    with open(settings_file, "a") as f:
        f.write("\nCOOKIES_FILE=cookies.txt\n")


def version_6() -> None:
    """Обновляет конфигурацию до версии 6."""
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"
    docker_settings_file = config_dir / "settings-docker.conf"
    with open(settings_file, "r+") as f:
        config = f.readlines()
        for i, line in enumerate(config):
            if line.startswith("DOWNLOADS_DIR"):
                config[i] = f"{line[:-1]}  # при запуске в докере путь всегда /downloads\n"
                break
        f.seek(0)
        f.writelines(config)
        f.truncate()
    if docker_settings_file.exists():
        try:
            os.remove(docker_settings_file)
        except Exception as e:
            logger.warning("Error removing %s: %s", docker_settings_file, e)


def version_7() -> None:
    """Обновляет конфигурацию до версии 7."""
    config_dir = get_config_dir()
    settings_file = config_dir / "settings.conf"

    download_from_tiktok = True
    tiktok_user = ""

    with open(settings_file, "r+") as f:
        config = f.readlines()
        new_lines = []
        for i, line in enumerate(config):
            if i + 1 < len(config) and config[i + 1].startswith("# Настройки тиктока"):
                continue
            if line.startswith("# Настройки тиктока"):
                continue
            if line.startswith("DOWNLOAD_FROM_TIKTOK"):
                download_from_tiktok = "true" in line.split("=")[1].strip()
                continue
            if line.startswith("TIKTOK_USER"):
                tiktok_user = line.split("=")[1].strip().replace('"', "")
            new_lines.append(line)
        f.seek(0)
        f.writelines(new_lines)
        f.truncate()

    if not download_from_tiktok and tiktok_user:
        logger.warning(
            "DOWNLOAD_FROM_TIKTOK was disabled, but TIKTOK_USER was set\n"
            "Removing TIKTOK_USER\n"
            "If you want to enable auto import from TikTok, set TIKTOK_USER in settings.conf"
        )
        set_config_value("TIKTOK_USER", "")


VERSIONS = [
    None,
    version_2,
    version_3,
    version_4,
    version_5,
    version_6,
    version_7,
]


def upgrade_config() -> None:
    """Обновляет конфигурацию до последней версии."""
    config_version = get_config_version()
    for i in range(config_version, len(VERSIONS)):
        logger.info("Upgrading config to version %s...", i + 1)
        VERSIONS[i]()
        set_config_value("CONFIG_VERSION", str(i + 1))


config_dir = load_config()

# Настройки импорта видео
TIKTOK_USER: str = os.getenv("TIKTOK_USER", "")
IMPORT_LIKED_VIDEOS: bool = os.getenv("IMPORT_LIKED_VIDEOS", "true").lower() == "true"
IMPORT_FAVORITE_VIDEOS: bool = os.getenv("IMPORT_FAVORITE_VIDEOS", "true").lower() == "true"

# Настройки Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
TELEGRAM_MAX_VIDEO_SIZE = 1024 * 1024 * 50 - 2048

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

if DOCKER:
    DOWNLOADS_DIR = "/downloads"
else:
    DOWNLOADS_DIR: str = os.getenv("DOWNLOADS_DIR", "./downloads")

TIKTOK_DATA_FILE: str = os.getenv("TIKTOK_DATA_FILE", "user_data_tiktok.json")
if not os.path.isabs(TIKTOK_DATA_FILE):
    TIKTOK_DATA_FILE = str(config_dir / TIKTOK_DATA_FILE)

# Файл с cookies в формате Netscape для yt-dlp
COOKIES_FILE: str | None = os.getenv("COOKIES_FILE", "cookies.txt")
if not os.path.isabs(COOKIES_FILE):
    COOKIES_FILE = str(config_dir / COOKIES_FILE)
    if not os.path.exists(COOKIES_FILE):
        COOKIES_FILE = None

SLIDESHOW_TMP_DIR: Path = Path(tempfile.gettempdir()) / "gallery_dl"
PARTS_TMP_DIR: Path = Path(tempfile.gettempdir()) / "video_parts"

os.makedirs(SLIDESHOW_TMP_DIR, exist_ok=True)
os.makedirs(PARTS_TMP_DIR, exist_ok=True)
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
