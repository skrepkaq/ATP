import argparse
import logging
import time

import schedule

from atp.check_availability import check_video_batch
from atp.database import run_migrations
from atp.download import download_new_videos
from atp.settings import DOWNLOAD_FROM_TIKTOK
from atp.telegram import discover_chat_id
from atp.video_import import import_from_file, import_from_tiktok

logger = logging.getLogger(__name__)


def run_download_from_file() -> None:
    """Импортирует видео из json файла и скачивает их"""
    import_from_file()
    download_new_videos()


def run_download_from_tiktok() -> None:
    """Импортирует видео из TikTok и скачивает их"""
    import_from_tiktok()
    download_new_videos()


def run_scheduler() -> None:
    """Основной цикл работы приложения"""
    run_migrations()
    discover_chat_id()

    schedule.every().hour.at("00:00").do(check_video_batch)

    if DOWNLOAD_FROM_TIKTOK:
        schedule.every().hour.at("30:00").do(run_download_from_tiktok)

    logger.info("ATP archiver has been started!")
    while True:
        schedule.run_pending()
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--download-from-file",
        action="store_true",
        help="Import videos from json file and download them",
    )
    args = parser.parse_args()

    if args.download_from_file:
        run_migrations()
        run_download_from_file()
        return

    run_scheduler()


if __name__ == "__main__":
    main()
