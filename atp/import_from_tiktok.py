"""
Модуль для импорта видео из TikTok.

Модуль выполняет:
- Импорт лайкнутых видео из TikTok
- Добавление новых видео в базу данных
- Запуск процесса скачивания
"""

import asyncio
import math

from playwright.async_api import async_playwright
from TikTokApi import TikTokApi
from TikTokApi.helpers import random_choice

from atp import crud
from atp.database import get_db_session
from atp.download import download
from atp.settings import BROWSERLESS_URL, TIKTOK_USER


class CDPTikTokApi(TikTokApi):
    """TikTok API с поддержкой Chrome DevTools Protocol."""

    async def create_sessions(
        self,
        cdp_url,
        num_sessions=5,
        ms_tokens=None,
        proxies=None,
        sleep_after=1,
        starting_url="https://www.tiktok.com",
        context_options=None,
        cookies=None,
        suppress_resource_load_types=None,
        timeout=30000,
    ):
        """
        Расширяет TikTokApi.create_sessions с поддержкой connect_over_cdp.
        """
        context_options = context_options or {}
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.connect_over_cdp(
            cdp_url + '?launch={"stealth": true}'
        )

        await asyncio.gather(
            *(
                self._TikTokApi__create_session(
                    proxy=random_choice(proxies),
                    ms_token=random_choice(ms_tokens),
                    url=starting_url,
                    context_options=context_options,
                    sleep_after=sleep_after,
                    cookies=random_choice(cookies),
                    suppress_resource_load_types=suppress_resource_load_types,
                    timeout=timeout,
                )
                for _ in range(num_sessions)
            )
        )


async def import_from_tiktok() -> None:
    db = get_db_session()

    videos = crud.get_all_videos(db)
    if not videos:
        print("No videos in DB. Please import using import_from_file.py")
        # Удалить чтобы импортировать все видео из тиктока а не файла
        # (дольше и только лайкнутые без сохранённых)
        return

    video_ids: set[str] = {v.id for v in videos}

    try:
        async with CDPTikTokApi() as api:
            await api.create_sessions(
                cdp_url=BROWSERLESS_URL, ms_tokens=[None], num_sessions=1, sleep_after=3
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
    except Exception as e:
        print(f"Error importing from TikTok: {e}")
    db.close()

    # Запускаем скачивание новых видео
    download()


if __name__ == "__main__":
    asyncio.run(import_from_tiktok())
