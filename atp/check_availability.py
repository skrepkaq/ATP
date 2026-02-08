"""
Модуль для проверки доступности архивированных видео TikTok.

Этот скрипт:
1. Получает партию видео для проверки (сначала самые старые проверенные видео)
2. Проверяет, доступно ли еще каждое видео
3. Обновляет статус видео, которые больше недоступны и отправляет их в Telegram
4. Обновляет last_checked для всех проверенных видео
5. Проверяет восстановленные видео и удаляет уведомления из Telegram
"""

import math

from atp import crud
from atp.database import get_db_session
from atp.models import Video
from atp.settings import CHECK_INTERVAL_DAYS
from atp.telegram_notifier import handle_video_restoration, send_video_deleted_notification
from atp.ytdlp import NetworkError, check_video_availability


def check_video_batch() -> None:
    """Проверяет партию видео на доступность"""
    db = get_db_session()

    try:
        total_videos = db.query(Video).filter(Video.status.in_(["success", "deleted"])).count()

        if total_videos == 0:
            print("No videos to check")
            return

        # Рассчитываем, сколько видео проверять в этой партии
        # Формула: всего видео / дней / часов = видео в час
        videos_per_batch = math.ceil(total_videos / CHECK_INTERVAL_DAYS / 24)

        print(f"Checking {videos_per_batch} videos out of {total_videos} total")

        videos = crud.get_videos_to_check(db, videos_per_batch)
        unavailable_count = 0
        restored_count = 0

        for video in videos:
            print(f"Checking video {video.id} ({video.name or 'Unknown'})")

            try:
                available, error_msg = check_video_availability(video.id)
            except NetworkError:
                print("Encountered a network error, skipping")
                continue

            if available:
                if video.status == "deleted":
                    print(f"Video {video.id} has been restored!")
                    restored_count += 1
                    if video.message_id:
                        print(f"Deleting message {video.message_id}")
                        if not handle_video_restoration(video):
                            continue
                    crud.update_video_message_id(db, video.id, None)
                    crud.update_video_status(db, video.id, "success")
            elif video.status == "success":
                print(f"Video {video.id} is no longer available!")
                unavailable_count += 1

                if not (msg_id := send_video_deleted_notification(video)):
                    continue
                crud.update_video_message_id(db, video.id, msg_id)
                crud.update_video_status(db, video.id, "deleted")

            crud.update_video_deleted_reason(db, video.id, error_msg)
            crud.update_video_last_checked(db, video.id)

        print(f"Checked {len(videos)} videos")
        print(f"Found {unavailable_count} unavailable videos")
        print(f"Found {restored_count} restored videos")

    except Exception as e:
        print(f"Error checking videos: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    check_video_batch()
