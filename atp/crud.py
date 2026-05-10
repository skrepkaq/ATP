from datetime import datetime

from sqlalchemy.orm import Session

from atp.models import Video, VideoInfo


def add_video_to_db(
    db: Session, video_id: str, date: datetime, liked: bool = False, saved: bool = False
) -> Video:
    """Добавляет видео в базу данных, если оно не существует.

    :param db: Сессия базы данных
    :param video_id: ID видео
    :param date: Дата добавления

    :return: Объект видео в базе данных
    """
    db_video = db.query(Video).filter(Video.id == video_id).first()

    if not db_video:
        db_video = Video(id=video_id, date=date, liked=liked, saved=saved)
        db.add(db_video)
        db.commit()

    return db_video


def add_videos_bulk(db: Session, videos: list[VideoInfo]) -> None:
    """Добавляет список видео в базу данных.

    :param db: Сессия базы данных
    :param videos: Список объектов VideoInfo
    """
    for video in videos:
        if db.query(Video).filter(Video.id == video.id).first():
            continue
        db_video = Video(id=video.id, date=video.date, liked=video.liked, saved=video.saved)
        db.add(db_video)

    db.commit()


def update_video_sources_bulk(db: Session, videos: list[VideoInfo]) -> None:
    """Обновляет источники видео в базе данных.

    :param db: Сессия базы данных
    :param videos: Список объектов VideoInfo
    """
    for video in videos:
        db_video = db.query(Video).filter(Video.id == video.id).first()
        if not db_video:
            continue
        if not db_video.liked and video.liked:
            db_video.liked = True
        if not db_video.saved and video.saved:
            db_video.saved = True

    db.commit()


def get_videos(db: Session, status: list[str] | None = None) -> list[Video]:
    """Получает список видео из базы данных.

    :param db: Сессия базы данных
    :param status: Список статусов видео
    :return: Список объектов видео
    """
    videos = db.query(Video)
    if status:
        videos = videos.filter(Video.status.in_(status))
    return videos.all()


def update_video(
    db: Session,
    video: Video,
    update_last_checked: bool = True,
    **kwargs: str | None,
) -> bool:
    """Обновляет информацию о видео в базе данных.
    :param db: Сессия базы данных
    :param video: Объект видео
    :param update_last_checked: Обновлять ли дату последней проверки доступности

    :param name: Название видео
    :param date: Дата публикации/лайка видео
    :param status: Статус видео
    :param type: Тип видео
    :param author: Автор видео
    :param liked: Лайкнуто ли видео
    :param saved: Сохранено ли видео
    :param created_at: Дата создания записи
    :param last_checked: Дата последней проверки доступности
    :param message_id: ID сообщения об удалении видео
    :param deleted_reason: Причина недоступности видео

    :return: True если успешно, False если видео не найдено
    """
    for key, value in kwargs.items():
        if key in ["liked", "saved"] and not value:
            # Никогда не обновляем liked и saved на False
            continue
        setattr(video, key, value)
    if update_last_checked:
        video.last_checked = datetime.now()
    db.commit()
    return True
