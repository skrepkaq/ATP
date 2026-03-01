import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from atp import crud, video_import
from atp.models import Video


@pytest.mark.integration
def test_import_from_file_adds_videos(
    sqlite_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "Your Activity": {
            "Favorite Videos": {"FavoriteVideoList": []},
            "Like List": {
                "ItemFavoriteList": [
                    {"date": "2025-01-02 10:00:00", "link": "https://www.tiktok.com/@u/video/2/"}
                ]
            },
        }
    }
    src = tmp_path / "data.json"
    src.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", str(src))
    monkeypatch.setattr(video_import, "IMPORT_FAVORITE_VIDEOS", False)
    monkeypatch.setattr(video_import, "IMPORT_LIKED_VIDEOS", True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)

    video_import.import_from_file()

    all_videos = crud.get_videos(sqlite_session)
    assert len(all_videos) == 1
    assert all_videos[0].id == "2"


@pytest.mark.integration
def test_import_from_tiktok_stops_when_recent_20_are_known(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = [Video(id=f"known{i}", date=datetime(2025, 1, 1)) for i in range(20)]
    sqlite_session.add_all(existing)
    sqlite_session.commit()

    feed = [{"id": f"known{i}", "timestamp": 1735689600} for i in range(20)]

    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "u")
    monkeypatch.setattr(video_import, "get_user_liked_videos", lambda _u: feed)

    video_import.import_from_tiktok()

    assert len(crud.get_videos(sqlite_session)) == 20
