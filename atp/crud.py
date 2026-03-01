from datetime import datetime

from sqlalchemy.orm import Session

from atp.models import Video


def add_video_to_db(db: Session, video_id: str, date: datetime) -> Video:
    """Добавляет видео в базу данных, если оно не существует.

    :param db: Сессия базы данных
    :param video_id: ID видео
    :param date: Дата добавления

    :return: Объект видео в базе данных
    """
    db_video = db.query(Video).filter(Video.id == video_id).first()

    if not db_video:
        db_video = Video(id=video_id, date=date)
        db.add(db_video)
        db.commit()

    return db_video


def add_videos_bulk(db: Session, videos: list[dict[str, datetime]]) -> None:
    """Добавляет список видео в базу данных.

    :param db: Сессия базы данных
    :param videos: Список словарей с информацией о видео
    """
    for video in videos:
        if db.query(Video).filter(Video.id == video["id"]).first():
            continue
        db_video = Video(id=video["id"], date=video["date"])
        db.add(db_video)

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
    **kwargs: str | None,
) -> bool:
    """Обновляет информацию о видео в базе данных.
    :param db: Сессия базы данных
    :param video: Объект видео
    :param name: Название видео
    :param date: Дата публикации/лайка видео
    :param status: Статус видео
    :param type: Тип видео
    :param author: Автор видео
    :param created_at: Дата создания записи
    :param last_checked: Дата последней проверки доступности
    :param message_id: ID сообщения об удалении видео
    :param deleted_reason: Причина недоступности видео
    :return: True если успешно, False если видео не найдено
    """
    video.last_checked = datetime.now()
    for key, value in kwargs.items():
        setattr(video, key, value)
    db.commit()
    return True
