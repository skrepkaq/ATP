"""
Модуль для скачивания видео TikTok.

Модуль выполняет:
- Скачивание `new` видео из базы данных
- Обновление статусов видео в базе данных
"""

import os

from atp import crud
from atp.database import get_db_session
from atp.settings import DOWNLOADS_DIR, HOPE_MODE
from atp.ytdlp import download_video


def download() -> None:
    """Скачивает новые видео TikTok"""
    os.makedirs(DOWNLOADS_DIR, exist_ok=True)

    db = get_db_session()

    try:
        videos = crud.get_all_videos(db, status="new")
        if HOPE_MODE:
            print(
                "HOPE_MODE is enabled, will try to download failed videos. This may take a while."
            )
            videos.extend(crud.get_all_videos(db, status="failed"))
        print(f"Found {len(videos)} new{' or failed' if HOPE_MODE else ''} videos")

        if not videos:
            return

        success_count = 0
        for i, video in enumerate(videos):
            print(f"Downloading video {i + 1}/{len(videos)}: {video.id}")

            if download_video(db, video.id):
                success_count += 1
                print(f"Successfully downloaded video {video.id}")
            else:
                print(f"Failed to download video {video.id}")

        print(f"Downloaded {success_count}/{len(videos)} videos")
        if new_left := crud.get_all_videos(db, status="new"):
            print(f"{len(new_left)} videos with status `new` remaining")
        if HOPE_MODE:
            print("Don't forget to disable HOPE_MODE in settings.conf!")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    download()
