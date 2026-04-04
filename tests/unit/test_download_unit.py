from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from atp import download
from atp.models import Video, VideoStatus


@pytest.mark.unit
def test_download_new_videos_returns_early_when_empty(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(download, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(download, "HOPE_MODE", False)
    called = {"download": False}
    monkeypatch.setattr(
        download,
        "download_video",
        lambda _video: called.__setitem__("download", True),
    )
    download.download_new_videos()
    assert called["download"] is False


@pytest.mark.unit
def test_download_new_videos_handles_top_level_exception(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(Video(id="v1", date=datetime(2025, 1, 1), status=VideoStatus.NEW))
    sqlite_session.commit()

    monkeypatch.setattr(download, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(download, "HOPE_MODE", False)
    monkeypatch.setattr(
        download,
        "download_video",
        lambda _video: (_ for _ in ()).throw(RuntimeError("broken")),
    )

    # Must not raise because function has top-level exception handling.
    download.download_new_videos()
