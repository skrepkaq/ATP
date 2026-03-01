from pathlib import Path

from alembic import command
from alembic import config as alembic_config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

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
        Path(__file__).parent / "alembic.ini",
        config_args={"sqlalchemy.url": DATABASE_URL},
    )
    # Keep application logging config; let Alembic skip fileConfig()
    # when migrations are triggered from the app runtime.
    alembic_cfg.attributes["skip_alembic_logging_config"] = True
    command.upgrade(alembic_cfg, "head")
