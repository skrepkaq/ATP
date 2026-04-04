from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from atp import crud, download
from atp.models import Video, VideoStatus, VideoType


@pytest.mark.integration
def test_download_new_videos_updates_statuses(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add_all(
        [
            Video(id="ok", date=datetime(2025, 1, 1), status=VideoStatus.NEW),
            Video(id="deleted", date=datetime(2025, 1, 1), status=VideoStatus.NEW),
            Video(id="skip", date=datetime(2025, 1, 1), status=VideoStatus.NEW),
        ]
    )
    sqlite_session.commit()

    monkeypatch.setattr(download, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(download, "HOPE_MODE", False)

    def fake_download(video: Video):
        if video.id == "ok":
            return SimpleNamespace(
                name="n1",
                author="a1",
                type=VideoType.VIDEO,
                deleted_reason=None,
            )
        if video.id == "deleted":
            return SimpleNamespace(
                name="n2",
                author="a2",
                type=VideoType.SLIDESHOW,
                deleted_reason="gone(r)",
            )
        return None

    monkeypatch.setattr(download, "download_video", fake_download)

    download.download_new_videos()

    videos = {v.id: v for v in crud.get_videos(sqlite_session)}
    assert videos["ok"].status == VideoStatus.SUCCESS
    assert videos["deleted"].status == VideoStatus.FAILED
    assert videos["deleted"].deleted_reason == "gone(r)"
    assert videos["skip"].status == VideoStatus.NEW


@pytest.mark.integration
def test_download_new_videos_includes_failed_in_hope_mode(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add_all(
        [
            Video(id="n1", date=datetime(2025, 1, 1), status=VideoStatus.NEW),
            Video(id="f1", date=datetime(2025, 1, 1), status=VideoStatus.FAILED),
        ]
    )
    sqlite_session.commit()

    monkeypatch.setattr(download, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(download, "HOPE_MODE", True)
    monkeypatch.setattr(
        download,
        "download_video",
        lambda _video: SimpleNamespace(
            name="x",
            author="y",
            type=VideoType.VIDEO,
            deleted_reason=None,
        ),
    )

    download.download_new_videos()

    by_id = {v.id: v for v in crud.get_videos(sqlite_session)}
    assert by_id["n1"].status == VideoStatus.SUCCESS
    assert by_id["f1"].status == VideoStatus.SUCCESS
