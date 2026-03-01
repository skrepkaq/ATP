"""
Модуль для импорта видео TikTok из файла экспорта JSON.

Модуль выполняет:
- Загрузку данных из JSON-файла экспорта TikTok
- Обработку списка лайкнутых и сохраненных видео
- Импорт видео в базу данных
- Запуск процесса скачивания
Модуль выполняет:
- Импорт лайкнутых видео из TikTok
- Добавление новых видео в базу данных
- Запуск процесса скачивания
"""

import json
import logging
import os
import sys
from datetime import datetime

from atp import crud
from atp.database import get_db_session, run_migrations
from atp.download import download_new_videos
from atp.settings import IMPORT_FAVORITE_VIDEOS, IMPORT_LIKED_VIDEOS, TIKTOK_DATA_FILE, TIKTOK_USER
from atp.tiktok import get_user_liked_videos

logger = logging.getLogger(__name__)


def parse_tiktok_json_file(file: str) -> list[dict[str, datetime]] | None:
    """Загружает список видео из JSON-файла экспорта TikTok.

    :param file: Путь к JSON-файлу с данными экспорта

    :return: Список словарей с информацией о видео
    """
    with open(file, encoding="utf-8") as f:
        data = json.load(f)

    try:
        activity = data.get("Likes and Favorites") or data.get("Your Activity")
        videos_raw = (
            activity["Favorite Videos"]["FavoriteVideoList"]
            if IMPORT_FAVORITE_VIDEOS
            else []
        ) + (
            activity["Like List"]["ItemFavoriteList"]
            if IMPORT_LIKED_VIDEOS
            else []
        )  # fmt: skip
    except (KeyError, TypeError) as e:
        logger.error("JSON error: %s", e)
        return None

    videos: list[dict[str, datetime]] = []
    ids: set[str] = set()
    for video in videos_raw:
        date_str = video.get("date") or video["Date"]
        date = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")

        video_link = video.get("link") or video["Link"]
        video_id = video_link.split("/")[-2]

        if video_id in ids:
            continue

        ids.add(video_id)
        videos.append({"id": video_id, "date": date})

    return sorted(videos, key=lambda v: v["date"])


def import_from_file() -> None:
    if not os.path.exists(TIKTOK_DATA_FILE):
        logger.error("Error: file %s does not exists", TIKTOK_DATA_FILE)
        return

    db = get_db_session()

    try:
        videos = parse_tiktok_json_file(TIKTOK_DATA_FILE)
        if not videos:
            logger.info(
                "No videos found in %s "
                "(check IMPORT_FAVORITE_VIDEOS/IMPORT_LIKED_VIDEOS and export data)",
                TIKTOK_DATA_FILE,
            )
            return

        try:
            crud.add_videos_bulk(db, videos)
            logger.info("Added/checked %s videos", len(videos))
        except Exception as e:
            logger.exception("Error importing videos: %s", e)

    except Exception as e:
        logger.exception("Error importing from file: %s", e)
    finally:
        db.close()


def import_from_tiktok() -> None:
    db = get_db_session()

    videos = crud.get_videos(db)
    if not videos:
        logger.info("No videos in DB. Please import using import_from_file.py")
        # Удалить чтобы импортировать все видео из тиктока а не файла
        # (дольше и только лайкнутые без сохранённых)
        return

    video_ids: set[str] = {v.id for v in videos}

    try:
        new_videos: list[str] = []
        for video in get_user_liked_videos(TIKTOK_USER):
            new_videos.append(video["id"])

            if video["id"] not in video_ids:
                logger.info("Import video %s", video["id"])
                crud.add_video_to_db(db, video["id"], datetime.fromtimestamp(video["timestamp"]))

            if len(new_videos) >= 20 and set(new_videos[-20:]).issubset(video_ids):
                # Все 20 последних видео уже есть в БД, ливаем
                logger.info("No new videos, exiting")
                break
    except Exception as e:
        logger.exception("Error importing from TikTok: %s", e)
    db.close()


if __name__ == "__main__":
    """Обратная совместимость для запуска через python -um atp.import_from_file"""
    import time

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(levelname)s [%(name)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logger.warning(
        "\nPlease update `atp-from-file` entrypoint in compose.yaml to "
        '["python", "-m", "atp", "--download-from-file"]\n'
        "Or download a new version from https://github.com/skrepkaq/ATP/blob/master/compose.yaml\n"
        "Old entrypoint will still work, but it's deprecated and will be removed in the future"
    )
    time.sleep(5)
    run_migrations()
    import_from_file()
    download_new_videos()
