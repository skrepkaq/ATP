"""
Модуль для импорта видео из TikTok.

Модуль выполняет:
- Импорт лайкнутых видео из TikTok
- Добавление новых видео в базу данных
- Запуск процесса скачивания
"""

from datetime import datetime

from atp import crud
from atp.database import get_db_session
from atp.download import download
from atp.settings import TIKTOK_USER
from atp.ytdlp import get_user_liked_videos


def import_from_tiktok() -> None:
    db = get_db_session()

    videos = crud.get_all_videos(db)
    if not videos:
        print("No videos in DB. Please import using import_from_file.py")
        # Удалить чтобы импортировать все видео из тиктока а не файла
        # (дольше и только лайкнутые без сохранённых)
        return

    video_ids: set[str] = {v.id for v in videos}

    try:
        new_videos: list[str] = []
        for video in get_user_liked_videos(TIKTOK_USER):
            new_videos.append(video["id"])

            if video["id"] not in video_ids:
                print(f"Import video {video['id']}")
                crud.add_video_to_db(db, video["id"], datetime.fromtimestamp(video["timestamp"]))

            if len(new_videos) >= 20 and set(new_videos[-20:]).issubset(video_ids):
                # Все 20 последних видео уже есть в БД, ливаем
                print("No new videos, exiting")
                break
    except Exception as e:
        print(f"Error importing from TikTok: {e}")
    db.close()

    # Запускаем скачивание новых видео
    download()


if __name__ == "__main__":
    import_from_tiktok()
