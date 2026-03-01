from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from atp import database, settings

EXPECTED_VIDEO_COLUMNS = {
    "id",
    "name",
    "date",
    "status",
    "created_at",
    "updated_at",
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
