from datetime import datetime

from sqlalchemy.orm import Session

from atp.models import Video


def add_video_to_db(
    db: Session,
    video_id: str,
    date: datetime,
    author: str | None = None,
    status: str = "new",
) -> Video:
    """Добавляет видео в базу данных, если оно не существует.

    :param db: Сессия базы данных
    :param video_id: ID видео
    :param date: Дата добавления
    :param author: Автор видео
    :param status: Статус видео (по умолчанию: "new")

    :return: Объект видео в базе данных
    """
    db_video = db.query(Video).filter(Video.id == video_id).first()

    if not db_video:
        db_video = Video(id=video_id, date=date, status=status, author=author)
        db.add(db_video)
        db.commit()

    return db_video


def update_video_status(
    db: Session, video_id: str, status: str, name: str | None = None
) -> bool:
    """Обновляет статус видео в базе данных.

    :param db: Сессия базы данных
    :param video_id: ID видео
    :param status: Новый статус
    :param name: Название видео (опционально)

    :return: True если успешно, False если видео не найдено
    """
    db_video = db.query(Video).filter(Video.id == video_id).first()

    if db_video:
        db_video.status = status
        if name:
            db_video.name = name
        db.commit()
        return True

    return False


def update_video_last_checked(db: Session, video_id: str) -> bool:
    """Обновляет время последней проверки видео на текущее.

    :param db: Сессия базы данных
    :param video_id: ID видео

    :return: True если успешно, False если видео не найдено
    """
    db_video = db.query(Video).filter(Video.id == video_id).first()

    if db_video:
        db_video.last_checked = datetime.now()
        db.commit()
        return True

    return False


def get_videos_to_check(db: Session, limit: int) -> list[Video]:
    """Получает партию видео для проверки доступности.

    :param db: Сессия базы данных
    :param limit: Количество видео для проверки

    :return: Список объектов Video
    """
    return (
        db.query(Video)
        .filter(Video.status == "success")
        .order_by(Video.last_checked)
        .limit(limit)
        .all()
    )


def get_all_videos(db: Session, status: str | None = None) -> list[Video]:
    """Получает видео из базы данных с возможностью фильтрации по статусу.

    :param db: Сессия базы данных
    :param status: Статус видео для фильтрации (опционально)

    :return: Список объектов Video
    """
    videos = db.query(Video)
    if status:
        videos = videos.filter(Video.status == status)
    return videos.all()
