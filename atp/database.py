import os

from alembic import command
from alembic import config as alembic_config
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

from atp.settings import DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db_session() -> Session:
    """Получает сессию базы данных.

    :return: Сессия базы данных
    """
    return SessionLocal()


def run_migrations() -> None:
    """Запускает миграции Alembic до последней версии.

    Использует конфигурацию из alembic.ini и применяет все
    доступные миграции до последней версии.
    """
    alembic_cfg = alembic_config.Config(
        os.path.join(os.path.dirname(__file__), "alembic.ini"),
        config_args={"sqlalchemy.url": DATABASE_URL},
    )
    command.upgrade(alembic_cfg, "head")
