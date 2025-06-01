"""
Модуль для проверки доступности архивированных видео TikTok.

Этот скрипт:
1. Получает партию видео для проверки (сначала самые старые проверенные видео)
2. Проверяет, доступно ли еще каждое видео
3. Обновляет статус видео, которые больше недоступны и отправляет их в Telegram
4. Обновляет last_checked для всех проверенных видео
"""

import math

from atp.crud import (
    get_videos_to_check,
    update_video_last_checked,
    update_video_status,
)
from atp.database import get_db_session
from atp.models import Video
from atp.settings import CHECK_INTERVAL_DAYS
from atp.telegram_notifier import send_video_deleted_notification
from atp.ytdlp import NetworkError, check_video_availability


def check_video_batch() -> None:
    """Проверяет партию видео на доступность"""
    db = get_db_session()

    try:
        total_videos = db.query(Video).filter(Video.status == "success").count()

        if total_videos == 0:
            print("No videos to check")
            return

        # Рассчитываем, сколько видео проверять в этой партии
        # Формула: всего видео / дней / часов = видео в час
        videos_per_batch = math.ceil(total_videos / CHECK_INTERVAL_DAYS / 24)

        print(f"Checking {videos_per_batch} videos out of {total_videos} total")

        videos = get_videos_to_check(db, videos_per_batch)
        unavailable_count = 0

        for video in videos:
            print(f"Checking video {video.id} ({video.name or 'Unknown'})")

            try:
                available = check_video_availability(video.id)
            except NetworkError:
                print("Encountered a network error, skipping")

            if available:
                update_video_last_checked(db, video.id)
            elif video.status == "success":
                print(f"Video {video.id} is no longer available!")

                if send_video_deleted_notification(video):
                    update_video_status(db, video.id, "deleted")
                    update_video_last_checked(db, video.id)

                unavailable_count += 1

        print(f"Checked {len(videos)} videos")
        print(f"Found {unavailable_count} unavailable videos")

    except Exception as e:
        print(f"Error checking videos: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_video_batch()
