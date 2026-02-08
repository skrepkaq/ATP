from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from atp.database import Base


class Video(Base):
    """Модель для хранения информации о видео TikTok.

    :ivar id: Уникальный идентификатор видео
    :ivar name: Название видео
    :ivar date: Дата публикации/лайка видео
    :ivar status: Статус видео (new, success, deleted, failed)
    :ivar type: Тип видео (video, slideshow)
    :ivar author: Автор видео
    :ivar created_at: Дата создания записи
    :ivar updated_at: Дата последнего обновления записи
    :ivar last_checked: Дата последней проверки доступности
    :ivar message_id: ID сообщения об удалении видео
    :ivar deleted_reason: Причина недоступности видео
    """

    __tablename__ = "videos"

    id: str = Column(String, primary_key=True)
    name: str | None = Column(String, nullable=True)
    date: datetime = Column(DateTime, nullable=False)
    status: str = Column(String, nullable=False, default="new")
    type: str | None = Column(String, nullable=True)
    author: str | None = Column(String, nullable=True)
    created_at: datetime = Column(DateTime, default=lambda: datetime.now())
    updated_at: datetime = Column(
        DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now()
    )
    last_checked: datetime | None = Column(DateTime, nullable=True)
    message_id: int | None = Column(Integer, nullable=True)
    deleted_reason: str | None = Column(String, nullable=True)

    def __repr__(self) -> str:
        """Строковое представление объекта Video.

        :return: Строка с основными параметрами видео
        """
        return f"<Video(id={self.id}, status={self.status})>"
