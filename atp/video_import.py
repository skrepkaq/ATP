"""
Модуль для импорта видео TikTok

Модуль выполняет:
- Импорт видео из JSON-файла экспорта TikTok
- Импорт лайкнутых и сохранённых видео из TikTok
- Запуск процесса скачивания
"""

import json
import logging
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Literal

from atp import crud
from atp.database import get_db_session, run_migrations
from atp.download import download_new_videos
from atp.models import Video, VideoInfo
from atp.settings import (
    DOWNLOAD_LIKED_VIDEOS,
    DOWNLOAD_SAVED_VIDEOS,
    TIKTOK_DATA_FILE,
    TIKTOK_USER,
)
from atp.tiktok import get_user_liked_videos, get_user_saved_videos

logger = logging.getLogger(__name__)


def parse_tiktok_json_file(file: str) -> list[VideoInfo] | None:
    """Загружает список видео из JSON-файла экспорта TikTok.

    :param file: Путь к JSON-файлу с данными экспорта

    :return: Список объектов VideoInfo
    """
    with open(file, encoding="utf-8") as f:
        data = json.load(f)

    try:
        activity = (
            data.get("Likes and Favorites") or data.get("Your Activity") or data.get("Activity")
        )
        saved_videos = (
            activity["Favorite Videos"]["FavoriteVideoList"] if DOWNLOAD_SAVED_VIDEOS else []
        )
        liked_videos = (
            activity["Like List"]["ItemFavoriteList"] if DOWNLOAD_LIKED_VIDEOS else []
        )  # fmt: skip
    except (KeyError, TypeError) as e:
        logger.error("JSON error: %s", e)
        return None

    videos: dict[str, VideoInfo] = {}
    for source_videos, liked, saved in (
        (liked_videos, True, False),
        (saved_videos, False, True),
    ):
        for video in source_videos:
            date_str = video.get("date") or video["Date"]
            video_link = video.get("link") or video["Link"]

            date = datetime.fromisoformat(date_str)
            video_id = video_link.split("/")[-2]
            info = videos.get(video_id)
            if info:
                info.liked = info.liked or liked
                info.saved = info.saved or saved
            else:
                videos[video_id] = VideoInfo(id=video_id, date=date, liked=liked, saved=saved)

    return sorted(videos.values(), key=lambda v: v.date)


def import_from_file() -> None:
    db = get_db_session()

    try:
        db_videos: dict[str, Video] = {v.id: v for v in crud.get_videos(db)}

        if not os.path.exists(TIKTOK_DATA_FILE):
            if db_videos:
                logger.info("File %s does not exist, skipping import", Path(TIKTOK_DATA_FILE).name)
            else:
                logger.error(
                    "Cannot import video from file: %s does not exist\n"
                    "Please request your data from TikTok and extract %s to config/ directory\n"
                    "https://github.com/skrepkaq/ATP#экспорт-данных-из-tiktok",
                    Path(TIKTOK_DATA_FILE).name,
                    Path(TIKTOK_DATA_FILE).name,
                )
            return

        videos = parse_tiktok_json_file(TIKTOK_DATA_FILE)
        if not videos:
            logger.warning(
                "No videos were imported from %s\n"
                "Check DOWNLOAD_SAVED_VIDEOS/DOWNLOAD_LIKED_VIDEOS settings "
                "or re-request ALL your data from TikTok\n"
                "https://github.com/skrepkaq/ATP#экспорт-данных-из-tiktok",
                Path(TIKTOK_DATA_FILE).name,
            )
            return

        try:
            videos_to_add: list[VideoInfo] = []
            videos_to_update: list[VideoInfo] = []

            for video in videos:
                db_video = db_videos.get(video.id)
                if not db_video:
                    videos_to_add.append(video)
                elif (video.liked and not db_video.liked) or (video.saved and not db_video.saved):
                    # Никогда не обновляем liked и saved на False
                    videos_to_update.append(video)
            if videos_to_add:
                crud.add_videos_bulk(db, videos_to_add)
                logger.info("Added %s videos", len(videos_to_add))
            if videos_to_update:
                crud.update_video_sources_bulk(db, videos_to_update)
                logger.info("Updated sources for %s videos", len(videos_to_update))
        except Exception as e:
            logger.exception("Error importing videos: %s", e)

    except Exception as e:
        logger.exception("Error importing from file: %s", e)
    finally:
        db.close()


def import_from_tiktok_source(
    importer: Callable[[str], list[dict]], source: Literal["liked", "saved"]
) -> None:
    """Импортирует видео из источника TikTok.
    :param importer: Функция для получения списка видео
    :param source: Источник видео (liked или saved)

    Импортируем до тех пор пока видео не закончатся
    или пока не наткнёмся на 10 видео подряд которые уже есть в БД с тем же источником
      (видео уже были импортированы как лайкнутые/сохранённые)
    или пока не наткнёмся на 100 видео подряд которые уже есть в БД
      (вероятно видео уже были импортированы, но c другим/без источника.
       Теоретически может сломаться если сохранить N видео, потом одновременно
       лайкнуть и сохранить 100 видео, не лайкать больше ничего и запуcтить импорт.
       Тогда те самые N видео не будут импортированы.
       Если бы мы импортировали пока все статусы не будут актуальны
       первый импорт, когда у видео нет статуса, занял бы вечность)
    """
    db = get_db_session()

    try:
        videos = {v.id: v for v in crud.get_videos(db)}
        existing_videos: set[str] = set(videos.keys())
        existing_same_source_videos: set[str] = {
            id for id, video in videos.items() if getattr(video, source) is True
        }

        if not existing_same_source_videos:
            logger.info("No %s videos in DB. Please import using import_from_file.py", source)
            return

        new_videos: list[str] = []
        for video in importer(TIKTOK_USER):
            video = VideoInfo(
                id=video["id"],
                date=datetime.fromtimestamp(video["timestamp"]),
                liked=source == "liked",
                saved=source == "saved",
            )
            new_videos.append(video.id)

            if video.id not in existing_videos:
                logger.info("Importing video %s", video.id)
                crud.add_video_to_db(
                    db,
                    video.id,
                    video.date,
                    liked=video.liked,
                    saved=video.saved,
                )
            elif video.id not in existing_same_source_videos:
                logger.info("Updating video sources for %s", video.id)
                crud.update_video(
                    db,
                    videos[video.id],
                    update_last_checked=False,
                    liked=video.liked,
                    saved=video.saved,
                )

            if len(new_videos) >= 10 and set(new_videos[-10:]).issubset(
                existing_same_source_videos
            ):
                # Все 10 последних видео c тем же источником уже есть в БД, ливаем
                logger.info("No new %s videos, exiting", source)
                return
            if len(new_videos) >= 100 and set(new_videos[-100:]).issubset(existing_videos):
                # Все 100 последних видео уже есть в БД, ливаем
                logger.info("No new %s videos, exiting (long import)", source)
                return
    except Exception as e:
        logger.exception("Error importing %s videos from TikTok: %s", source, e)
    finally:
        db.close()


def import_from_tiktok() -> None:
    if DOWNLOAD_LIKED_VIDEOS:
        import_from_tiktok_source(get_user_liked_videos, "liked")
    if DOWNLOAD_SAVED_VIDEOS:
        import_from_tiktok_source(get_user_saved_videos, "saved")


def deprecated_run() -> None:
    """
    Обратная совместимость для запуска через
    python -um atp.import_from_file и python -m atp --download-from-file
    """
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logger.warning(
        "Deprecated run method!\n"
        "No more need to do `docker compose up atp-from-file`\n"
        "Import from file now works on `docker compose up`\n"
        "\nPlease remove `atp-from-file` service from compose.yaml\n"
        "Or download a new version from https://github.com/skrepkaq/ATP/blob/master/compose.yaml\n"
        "And just run `docker compose up`\n"
        "\nOld run method will still work, but it's deprecated and will be removed in the future"
    )
    time.sleep(5)
    run_migrations()
    import_from_file()
    download_new_videos()


if __name__ == "__main__":
    deprecated_run()
