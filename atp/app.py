import argparse
import logging
import sys
import time

import schedule

from atp import crud
from atp.check_availability import check_video_batch
from atp.database import get_db_session, run_migrations
from atp.download import download_new_videos
from atp.settings import TIKTOK_USER
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
    run_download_from_file()

    db = get_db_session()
    videos = crud.get_videos(db)
    db.close()
    if not videos:
        logger.error(
            "No videos were imported! Cannot start the archiver!\n"
            "Please fix the errors above and restart the application"
        )
        sys.exit(1)

    schedule.every().hour.at("00:00").do(check_video_batch)

    if TIKTOK_USER:
        schedule.every().hour.at("30:00").do(run_download_from_tiktok)
    else:
        logger.warning("TIKTOK_USER is missing! Importing videos from TikTok is disabled")

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
        from atp.video_import import deprecated_run

        return deprecated_run()

    run_scheduler()


if __name__ == "__main__":
    main()
