import asyncio
import sys
import time

import schedule

from atp.check_availability import check_video_batch
from atp.database import run_migrations
from atp.import_from_tiktok import import_from_tiktok
from atp.settings import DOWNLOAD_FROM_TIKTOK, MS_TOKEN

run_migrations()

# Проверка доступности видео
schedule.every().hour.at("00:00").do(check_video_batch)

if DOWNLOAD_FROM_TIKTOK:
    if not MS_TOKEN:
        print("MS_TOKEN is not provided, exiting")
        sys.exit()
    # Импорт лайкнутых видео из tiktok
    schedule.every().hour.at("30:00").do(lambda: asyncio.run(import_from_tiktok()))


if __name__ == "__main__":
    print("ATP archiver has been started!")
    while True:
        schedule.run_pending()
        time.sleep(1)
