import io
import logging
import math
import time
from pathlib import Path

from sqlalchemy.orm import Session

from atp import crud, settings
from atp.database import get_db_session
from atp.media import generate_bmp, get_file_size, split_video, temp_files_cleanup
from atp.models import Video, VideoStatus
from atp.settings import CHECK_INTERVAL_DAYS
from atp.telegram import edit_media, send_media
from atp.tiktok import check_video_availability

logger = logging.getLogger(__name__)


def _get_caption(video: Video) -> str:
    """Возвращает описание видео, ограничив его 1024 символами"""
    MAX_LENGTH = 1024
    author = video.author + "\n" if video.author else ""
    cut_name = video.name or ""
    total_length = len(author) + len(cut_name) + 11
    if total_length > MAX_LENGTH:
        diff = total_length - MAX_LENGTH
        cut_name = cut_name[: -diff - 3] + "..."
    caption = author + cut_name + "\n" + video.date.strftime("%d.%m.%Y")
    return caption


def _send_multipart_video(video_parts: list[Path], caption: str) -> int:
    """У телеграма есть ограничение для ботов на размер видео в 50МБ
    Поэтому если видео больше 50МБ, то его нужно разбить на части и отправить как медиа-группу
    Только вот ограничение на самом деле распространяется не на каждое видео, на весь POST запрос
    Поэтому нам приходится сначала отправить BMP заглушки,
    а потом, по одному заменять их на реальные видео части.
    """
    bmp_photos = [generate_bmp(str(video_file)) for video_file in video_parts]
    result = send_media(caption=caption, photos=bmp_photos)

    messages = result if isinstance(result, list) else [result]
    message_ids = [msg["message_id"] for msg in messages]

    for i, (msg_id, part_path) in enumerate(zip(message_ids, video_parts, strict=True)):
        with open(part_path, "rb") as video_file:
            video_data = io.BytesIO(video_file.read())

        part_caption = caption if i == 0 else ""

        success = edit_media(message_id=msg_id, caption=part_caption, video=video_data)
        if not success:
            logger.warning("Failed to replace placeholder with video part %s", i + 1)

        time.sleep(5)

    logger.info("Telegram notification sent and parts updated successfully.")
    return message_ids[0]


def _handle_unavailable(db: Session, video: Video) -> bool:
    logger.info("Video %s is no longer available!", video.id)

    video_path = Path(settings.DOWNLOADS_DIR) / f"{video.id}.mp4"
    if not video_path.exists():
        logger.error("Video file not found: %s", video_path)
        return False

    try:
        caption = _get_caption(video)

        video_len = get_file_size(video_path)
        if video_len > settings.TELEGRAM_MAX_VIDEO_SIZE:
            parts = math.ceil(video_len / (settings.TELEGRAM_MAX_VIDEO_SIZE * 0.9))
            parts = max(2, min(10, parts))  # от 2 до 10 частей

            logger.info("Video %s is too large, splitting it into %s parts", video.id, parts)
            video_parts = split_video(video_path, parts)
            if not video_parts:
                logger.error(
                    "Failed to split video. This should never happen. Create a GitHub issue"
                )
                return False
            msg_id = _send_multipart_video(video_parts, caption)
        else:
            with open(video_path, "rb") as video_file:
                video_data = io.BytesIO(video_file.read())
            result = send_media(caption=caption, video=video_data)
            msg_id = result["message_id"]
            logger.info("Telegram notification sent successfully.")

        return crud.update_video(db, video=video, message_id=msg_id, status=VideoStatus.DELETED)
    except Exception as e:
        logger.exception("Exception occurred while sending Telegram notification: %s", e)
        return False
    finally:
        temp_files_cleanup()


def _handle_restored(db: Session, video: Video) -> bool:
    logger.info("Video %s has been restored!", video.id)
    if video.message_id:
        logger.info("Deleting message %s", video.message_id)
        caption = f"[Видео](https://tiktok.com/@/video/{video.id}) было восстановлено!"

        success = edit_media(
            message_id=video.message_id,
            caption=caption,
            photo=generate_bmp(video.id),
            parse_mode="Markdown",
        )
        if not success:
            return False

    return crud.update_video(db, video=video, message_id=None, status=VideoStatus.SUCCESS)


def check_video_batch() -> None:
    """Проверяет партию видео на доступность"""
    db = get_db_session()

    try:
        all_videos = sorted(
            crud.get_videos(db, status=[VideoStatus.SUCCESS, VideoStatus.DELETED]),
            key=lambda v: (v.last_checked is not None, v.last_checked),
        )

        if not all_videos:
            logger.info("No videos to check")
            return

        # Рассчитываем, сколько видео проверять в этой партии
        # Формула: всего видео / дней / часов = видео в час
        videos_per_batch = math.ceil(len(all_videos) / CHECK_INTERVAL_DAYS / 24)

        logger.info("Checking %s videos out of %s total", videos_per_batch, len(all_videos))

        videos = all_videos[:videos_per_batch]
        unavailable_count = 0
        restored_count = 0

        for video in videos:
            logger.info("Checking video %s (%s)", video.id, video.name or "Unknown")

            if not (result := check_video_availability(video)):
                continue

            available = not result.deleted_reason
            if available:
                if video.status == VideoStatus.DELETED:
                    restored_count += 1
                    if not _handle_restored(db, video):
                        continue
            else:
                if video.status == VideoStatus.SUCCESS:
                    unavailable_count += 1
                    if not _handle_unavailable(db, video):
                        continue

            crud.update_video(db, video=video, deleted_reason=result.deleted_reason)

        logger.info("Checked %s videos", len(videos))
        logger.info("Found %s unavailable videos", unavailable_count)
        logger.info("Found %s restored videos", restored_count)

    except Exception as e:
        logger.exception("Error checking videos: %s", e)
    finally:
        db.close()


if __name__ == "__main__":
    check_video_batch()
