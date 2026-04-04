import logging

from atp import crud
from atp.database import get_db_session
from atp.models import VideoStatus
from atp.settings import HOPE_MODE
from atp.tiktok import download_video

logger = logging.getLogger(__name__)


def download_new_videos() -> None:
    """Скачивает новые видео TikTok"""
    db = get_db_session()

    try:
        videos = crud.get_videos(db, status=[VideoStatus.NEW])
        if HOPE_MODE:
            logger.info(
                "HOPE_MODE is enabled, will try to download failed videos. This may take a while."
            )
            videos.extend(crud.get_videos(db, status=[VideoStatus.FAILED]))
        if not videos:
            return

        logger.info("Found %s new%s videos", len(videos), " or failed" if HOPE_MODE else "")

        success_count = 0
        for i, video in enumerate(videos):
            logger.info("Downloading video %s/%s: %s", i + 1, len(videos), video.id)

            if not (result := download_video(video)):
                continue
            success = not result.deleted_reason
            status = VideoStatus.SUCCESS if success else VideoStatus.FAILED
            crud.update_video(
                db,
                video=video,
                status=status,
                name=result.name,
                author=result.author,
                type=result.type,
                deleted_reason=result.deleted_reason,
            )

            if success:
                success_count += 1
                logger.info("Successfully downloaded video %s", video.id)
            else:
                logger.warning("Failed to download video %s", video.id)

        logger.info("Downloaded %s/%s videos", success_count, len(videos))
        if new_left := crud.get_videos(db, status=[VideoStatus.NEW]):
            logger.info("%s videos with status `new` remaining", len(new_left))
        if HOPE_MODE:
            logger.info("Don't forget to disable HOPE_MODE in settings.conf!")

    except Exception as e:
        logger.exception("Error downloading videos: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    download_new_videos()
