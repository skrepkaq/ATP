"""
Модуль для инициализации конфигурации.

Автоматически создаёт директорию config и копирует example settings
при первом запуске приложения.
"""

import os
import re
import shutil
from pathlib import Path

DOCKER: bool = os.getenv("DOCKER", "0") == "1"


def _get_project_root() -> Path:
    """Определяет корень проекта.

    Корень проекта - это директория, содержащая compose.yaml и atp/
    (на три уровня выше от atp/config_init.py).

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
    if DOCKER:
        return Path("/config")
    return _get_project_root() / "config"


def initialize_config() -> Path:
    """Инициализирует директорию конфигурации.

    Создаёт директорию config, если её нет, и копирует
    example.settings.conf в settings.conf, если settings.conf не существует.

    :return: Путь к директории конфигурации
    """
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)

    init = False
    for settings_file in ["settings-docker.conf", "settings.conf"]:
        settings_path = config_dir / settings_file
        example_path = _get_project_root() / f"example.{settings_file}"
        if not settings_path.exists() and example_path.exists():
            shutil.copy2(example_path, settings_path)
            init = True
    upgrade_config()
    if init:
        print(
            f"Created {settings_path} from example. "
            "Please configure it before use and restart the application."
        )
        while True:
            import time

            time.sleep(1)

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


VERSIONS = [
    None,
    version_2,
]


def upgrade_config() -> None:
    """Обновляет конфигурацию до последней версии."""
    config_version = get_config_version()
    for i in range(config_version, len(VERSIONS)):
        print(f"Upgrading config to version {i + 1}...")
        VERSIONS[i]()
        set_config_value("CONFIG_VERSION", str(i + 1))
