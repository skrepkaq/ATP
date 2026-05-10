from datetime import datetime
from importlib import import_module
from pathlib import Path

import pytest
from alembic import command
from alembic import config as alembic_config
from sqlalchemy import Column, DateTime, String, create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

from atp import database, settings
from atp.models import Video, VideoStatus, VideoType

EXPECTED_VIDEO_COLUMNS = {
    "id",
    "name",
    "date",
    "status",
    "liked",
    "saved",
    "created_at",
    "last_checked",
    "type",
    "author",
    "message_id",
    "deleted_reason",
}


def _video_columns(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    inspector = inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("videos")}
    engine.dispose()
    return columns


def _alembic_upgrade(db_url: str, revision: str) -> None:
    alembic_cfg = alembic_config.Config(
        Path(database.__file__).parent / "alembic.ini",
        config_args={"sqlalchemy.url": db_url},
    )
    alembic_cfg.attributes["skip_alembic_logging_config"] = True
    command.upgrade(alembic_cfg, revision)


_LegacyBase = declarative_base()


class _VideoAtRevision001(_LegacyBase):
    """ORM model matching the videos table at revision 001 (initial schema, for seeding only)."""

    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    date = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


@pytest.mark.integration
def test_run_migrations_on_empty_db_creates_latest_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "migrations.db"
    db_url = f"sqlite:///{db_file}"

    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(database, "DATABASE_URL", db_url)

    database.run_migrations()
    assert _video_columns(db_url) == EXPECTED_VIDEO_COLUMNS


@pytest.mark.integration
def test_empty_db_migrations_do_not_need_legacy_backfill_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_file = tmp_path / "empty.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(database, "DATABASE_URL", db_url)

    database.run_migrations()

    assert db_file.exists()
    assert _video_columns(db_url) == EXPECTED_VIDEO_COLUMNS


@pytest.mark.integration
def test_run_migrations_is_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "idempotent.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(database, "DATABASE_URL", db_url)

    database.run_migrations()
    first = _video_columns(db_url)
    database.run_migrations()
    second = _video_columns(db_url)

    assert first == second == EXPECTED_VIDEO_COLUMNS


@pytest.mark.integration
def test_run_migrations_on_nonempty_db_preserves_and_transforms_videos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Seed data at revision 001, then upgrade to head with no Telegram JSON and empty downloads."""
    db_file = tmp_path / "seeded.db"
    db_url = f"sqlite:///{db_file}"
    empty_downloads = tmp_path / "empty_downloads"
    empty_downloads.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "DATABASE_URL", db_url)
    monkeypatch.setattr(database, "DATABASE_URL", db_url)
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(empty_downloads))
    migration_003 = import_module("atp.migrations.versions.003_add_video_type")
    monkeypatch.setattr(migration_003, "DOWNLOADS_DIR", str(empty_downloads))

    migration_007 = import_module("atp.migrations.versions.007_add_message_id_column")
    monkeypatch.setattr(migration_007, "load_messages", lambda: [])

    _alembic_upgrade(db_url, "001")

    now = datetime(2024, 1, 15, 12, 0, 0)
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        session.add_all(
            [
                _VideoAtRevision001(
                    id="v-success",
                    name="Success clip",
                    date=now,
                    status=VideoStatus.SUCCESS,
                    created_at=now,
                    updated_at=now,
                ),
                _VideoAtRevision001(
                    id="v-deleted",
                    name="Removed clip",
                    date=now,
                    status=VideoStatus.DELETED,
                    created_at=now,
                    updated_at=now,
                ),
                _VideoAtRevision001(
                    id="v-new",
                    name="Pending",
                    date=now,
                    status=VideoStatus.NEW,
                    created_at=now,
                    updated_at=None,
                ),
                _VideoAtRevision001(
                    id="v-failed",
                    name="Bad",
                    date=now,
                    status=VideoStatus.FAILED,
                    created_at=now,
                    updated_at=now,
                ),
            ]
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()

    _alembic_upgrade(db_url, "head")

    assert _video_columns(db_url) == EXPECTED_VIDEO_COLUMNS

    verify_engine = create_engine(db_url)
    VerifySession = sessionmaker(autocommit=False, autoflush=False, bind=verify_engine)
    vs = VerifySession()
    try:
        rows = {v.id: v for v in vs.query(Video).order_by(Video.id).all()}
        assert set(rows) == {"v-deleted", "v-failed", "v-new", "v-success"}

        assert rows["v-success"].type == VideoType.VIDEO
        assert rows["v-success"].message_id is None
        assert rows["v-success"].liked is False
        assert rows["v-success"].saved is False
        assert rows["v-success"].deleted_reason is None
        assert rows["v-success"].last_checked is None
        assert rows["v-success"].created_at == now

        assert rows["v-deleted"].type == VideoType.VIDEO
        assert rows["v-deleted"].message_id is None
        assert rows["v-deleted"].liked is False
        assert rows["v-deleted"].saved is False
        assert rows["v-deleted"].deleted_reason is None
        assert rows["v-deleted"].last_checked is None
        assert rows["v-success"].created_at == now

        assert rows["v-new"].type is None
        assert rows["v-new"].message_id is None
        assert rows["v-new"].deleted_reason is None
        assert rows["v-new"].last_checked is None
        assert rows["v-success"].created_at == now

        assert rows["v-failed"].type is None
        assert rows["v-failed"].message_id is None
        assert rows["v-failed"].deleted_reason is None
        assert rows["v-failed"].last_checked is None
        assert rows["v-success"].created_at == now
    finally:
        vs.close()
        verify_engine.dispose()
