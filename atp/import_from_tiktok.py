"""
Модуль для импорта видео из TikTok.

Модуль выполняет:
- Импорт лайкнутых видео из TikTok
- Добавление новых видео в базу данных
- Запуск процесса скачивания
"""

import asyncio
import math

from TikTokApi import TikTokApi
from TikTokApi.exceptions import EmptyResponseException, InvalidResponseException

from atp import crud
from atp.database import get_db_session
from atp.download import download
from atp.settings import MS_TOKEN, TIKTOK_USER
from atp.telegram_notifier import send_message


async def import_from_tiktok() -> None:
    async with TikTokApi() as api:
        db = get_db_session()

        videos = crud.get_all_videos(db)
        if not videos:
            print("No videos in DB. Please import using import_from_file.py")
            # Удалить чтобы импортировать все видео из тиктока а не файла (дольше и только лайкнутые без сохранённых)
            return

        video_ids: set[str] = set(v.id for v in videos)
        try:
            await api.create_sessions(
                ms_tokens=[MS_TOKEN],
                num_sessions=1,
                sleep_after=3,
                browser="chromium",
                headless=True,
                override_browser_args=[],  # не удалять, иначе docker взрывается и все умирают
            )

            new_videos: list[str] = []
            async for video in api.user(TIKTOK_USER).liked(count=math.inf):
                new_videos.append(video.id)

                if video.id not in video_ids:
                    print(f"Import video {video.id}")
                    crud.add_video_to_db(db, video.id, video.create_time)

                if len(new_videos) >= 20 and set(new_videos[-20:]).issubset(video_ids):
                    # Все 20 последних видео уже есть в БД, ливаем
                    print("No new videos, exiting")
                    break
        except EmptyResponseException as e:
            print(e)
            send_message("msToken is invalid")  # спамим в телегу что токен сломался
        except InvalidResponseException as e:
            print(e)
        db.close()

        # Запускаем скачивание новых видео
        download()


if __name__ == "__main__":
    asyncio.run(import_from_tiktok())
