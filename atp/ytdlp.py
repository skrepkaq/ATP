"""
Модуль для работы с yt-dlp и загрузки видео из TikTok.

Этот модуль предоставляет функции для:
- Загрузки видео с помощью yt-dlp
- Проверки доступности видео
- Обработки сетевых ошибок
- Обновления информации о видео в базе данных
"""

from datetime import datetime
from pathlib import Path

import yt_dlp
from sqlalchemy.orm import Session

from atp.models import Video
from atp.settings import DOWNLOADS_DIR, MAX_RETRIES
from atp.slideshow import download_slideshow


class NetworkError(Exception):
    """Исключение при сетевых ошибках."""

    pass


def yt_dlp_request(ydl_opts: dict[str, any], video_id: str, download: bool) -> dict[str, any]:
    """Выполняет запрос к yt-dlp с обработкой сетевых ошибок.

    :param ydl_opts: Опции для yt-dlp
    :param video_id: ID видео
    :param download: Флаг скачивания

    :return: Информация о видео

    :raises NetworkError: При сетевых ошибках
    :raises Exception: При других ошибках
    """
    network_errors = [
        "Read timed out",
        "Failed to resolve",
        "Connection reset by peer",
        "Max retries exceeded",
        "Temporary failure in name resolution",
        "Connection aborted",
        "Unable to download webpage",
        "Unable to extract webpage video data",
        "Unsupported URL",
    ]

    is_network_error = False
    exc = None
    for attempt in range(MAX_RETRIES):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(f"https://www.tiktok.com/@/video/{video_id}", download)
        except Exception as e:
            exc = e
            error_msg = str(e)
            print(f"Error checking video {video_id} (attempt {attempt + 1}/{MAX_RETRIES}): {e}")

            is_network_error = any(err in error_msg for err in network_errors)

    # Если достигли максимального количества попыток или не сетевая ошибка
    if is_network_error:
        print("Network error detected, skipping")
        raise NetworkError
    else:
        raise exc


def download_video(db: Session, video_id: str) -> bool | None:
    """Загружает видео TikTok.

    :param db: Сессия базы данных
    :param video_id: ID видео

    :return: True если загрузка успешна, False в противном случае, None при сетевой ошибке
    """
    ydl_opts = {
        "format": "best",
        "outtmpl": str(Path(DOWNLOADS_DIR) / f"{video_id}.mp4"),
        "quiet": False,
        "no_warnings": False,
    }

    try:
        info = yt_dlp_request(ydl_opts, video_id, download=True)
    except NetworkError:
        return None
    except Exception as e:
        print(f"Error downloading video {video_id}: {e}")
        info = False

    video: Video = db.query(Video).filter(Video.id == video_id).first()
    if video:
        video.status = "success" if info else "failed"
        video.name = info.get("description", f"Video {video_id}") if info else ""
        video.last_checked = datetime.now()
        video.type = "video"  # Устанавливаем тип по умолчанию как "video"

        # Если в видео есть информация об авторе и она отсутствует в базе
        if info and info.get("uploader") and not video.author:
            video.author = info["uploader"]

        db.commit()

        if info and info["format_id"] == "audio":
            if download_slideshow(video_id):
                video.type = "slideshow"
            else:
                video.status = "new"
                info = False
            db.commit()
    return bool(info)


def check_video_availability(video_id: str) -> bool:
    """Проверяет доступность видео TikTok.

    :param video_id: ID видео

    :return: True если видео доступно, False в противном случае

    :raises NetworkError: При сетевых ошибках
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        yt_dlp_request(ydl_opts, video_id, download=False)
        return True
    except NetworkError as e:
        raise NetworkError from e
    except Exception:
        return False
