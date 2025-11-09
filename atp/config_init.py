"""
Модуль для инициализации конфигурации.

Автоматически создаёт директорию config и копирует example settings
при первом запуске приложения.
"""

import re
import shutil
from pathlib import Path


def _get_project_root() -> Path:
    """Определяет корень проекта.

    Корень проекта - это директория, содержащая compose.yaml и atp/
    (на три уровня выше от atp/config_init.py).

    :return: Путь к корню проекта
    """
    return Path(__file__).parent.parent


def get_config_dir(docker: bool = False) -> Path:
    """Определяет путь к директории конфигурации.

    Проверяет наличие /config, если существует - использует его
    (случай когда volume смонтирован в Docker).
    Иначе использует config/ относительно корня проекта.

    :return: Путь к директории конфигурации
    """
    if docker:
        return Path("/config")
    return _get_project_root() / "config"


def initialize_config(docker: bool = False) -> Path:
    """Инициализирует директорию конфигурации.

    Создаёт директорию config, если её нет, и копирует
    example.settings.conf в settings.conf, если settings.conf не существует.

    :return: Путь к директории конфигурации
    """
    config_dir = get_config_dir(docker)
    config_dir.mkdir(parents=True, exist_ok=True)

    init = False
    for settings_file in ["settings-docker.conf", "settings.conf"]:
        settings_path = config_dir / settings_file
        example_path = _get_project_root() / f"example.{settings_file}"
        if not settings_path.exists() and example_path.exists():
            shutil.copy2(example_path, settings_path)
            init = True
    if init:
        print(
            f"Created {settings_path} from example. "
            "Please configure it before use and restart the application."
        )
        while True:
            import time

            time.sleep(1)

    return config_dir


def set_config_value(key: str, value: str, docker: bool) -> None:
    """Устанавливает значение в settings.conf.

    :param key: Ключ
    :param value: Значение
    """
    config_dir = get_config_dir(docker=docker)
    settings_file = config_dir / "settings.conf"
    with open(settings_file, "r+") as f:
        config = f.read()
        config = re.sub(rf"{key}=.*", f"{key}={value}", config)
        f.seek(0)
        f.write(config)
        f.truncate()
