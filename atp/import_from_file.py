"""
Модуль для импорта видео TikTok из файла экспорта JSON.

Модуль выполняет:
- Загрузку данных из JSON-файла экспорта TikTok
- Обработку списка лайкнутых и сохраненных видео
- Импорт видео в базу данных
- Запуск процесса скачивания
"""

import json
import os
from datetime import datetime

from atp import crud
from atp.database import get_db_session, run_migrations
from atp.download import download
from atp.settings import IMPORT_FAVORITE_VIDEOS, IMPORT_LIKED_VIDEOS, TIKTOK_DATA_FILE


def load_videos_from_file(file: str) -> list[dict[str, str | datetime]] | None:
    """Загружает список видео из JSON-файла экспорта TikTok.

    :param file: Путь к JSON-файлу с данными экспорта

    :return: Список словарей с информацией о видео
    """
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    try:
        videos_raw = (
            data["Your Activity"]["Favorite Videos"]["FavoriteVideoList"]
            if IMPORT_FAVORITE_VIDEOS
            else []
        ) + (
            data["Your Activity"]["Like List"]["ItemFavoriteList"]
            if IMPORT_LIKED_VIDEOS
            else []
        )
    except (KeyError, TypeError) as e:
        print(f"JSON error: {e}")
        return None

    videos: list[dict[str, str | datetime]] = []
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
    run_migrations()

    if not os.path.exists(TIKTOK_DATA_FILE):
        print(f"Error: file {TIKTOK_DATA_FILE} does not exists")
        return

    db = get_db_session()

    try:
        videos = load_videos_from_file(TIKTOK_DATA_FILE)
        if not videos:
            return

        added_count = 0
        for video in videos:
            try:
                print(
                    "\033[1A\r\033[K"
                    + f"Import videos: {added_count: >{len(videos) % 10}}/{len(videos)}",
                    flush=True,
                )
                crud.add_video_to_db(db, video["id"], video["date"])  # TODO: make faster
                added_count += 1
            except Exception as e:
                print(f"Error importing video: {e}")

        print(f"Added/checked {added_count} videos")

    except Exception as e:
        print(f"Error importing from file: {e}")
    finally:
        db.close()

    # Запускаем скачивание новых видео
    download()


if __name__ == "__main__":
    import_from_file()
