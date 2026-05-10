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
    monkeypatch.setattr(video_import, "DOWNLOAD_SAVED_VIDEOS", False)
    monkeypatch.setattr(video_import, "DOWNLOAD_LIKED_VIDEOS", True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)

    video_import.import_from_file()

    all_videos = crud.get_videos(sqlite_session)
    assert len(all_videos) == 1
    assert all_videos[0].id == "2"


@pytest.mark.integration
def test_import_from_file_updates_liked_flag_for_existing_video(
    sqlite_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crud.add_video_to_db(sqlite_session, "2", datetime(2025, 1, 1), liked=False, saved=False)

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
    monkeypatch.setattr(video_import, "DOWNLOAD_SAVED_VIDEOS", False)
    monkeypatch.setattr(video_import, "DOWNLOAD_LIKED_VIDEOS", True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)

    video_import.import_from_file()

    v = crud.get_videos(sqlite_session)[0]
    assert v.id == "2"
    assert v.liked
    assert not v.saved


@pytest.mark.integration
def test_import_from_file_updates_saved_flag_for_existing_video(
    sqlite_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    crud.add_video_to_db(sqlite_session, "2", datetime(2025, 1, 1), liked=True, saved=False)

    payload = {
        "Your Activity": {
            "Favorite Videos": {
                "FavoriteVideoList": [
                    {"date": "2025-01-02 10:00:00", "link": "https://www.tiktok.com/@u/video/2/"}
                ]
            },
            "Like List": {"ItemFavoriteList": []},
        }
    }
    src = tmp_path / "data.json"
    src.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", str(src))
    monkeypatch.setattr(video_import, "DOWNLOAD_SAVED_VIDEOS", True)
    monkeypatch.setattr(video_import, "DOWNLOAD_LIKED_VIDEOS", False)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)

    video_import.import_from_file()

    v = crud.get_videos(sqlite_session)[0]
    assert v.id == "2"
    assert v.liked
    assert v.saved


@pytest.mark.integration
def test_import_from_tiktok_adds_and_updates_videos(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    existing = [Video(id="known", date=datetime(2025, 1, 1), liked=True, saved=True)] + [
        Video(id=f"known-{i}", date=datetime(2025, 1, 1), liked=True, saved=False)
        for i in range(20)
    ]
    sqlite_session.add_all(existing)
    sqlite_session.commit()

    feed_liked = [{"id": f"new-liked-{i}", "timestamp": 1735689600} for i in range(20)] + [
        {"id": f"known-{i}", "timestamp": 1735689600} for i in range(20)
    ]
    feed_saved = [{"id": f"new-saved-{i}", "timestamp": 1735689600} for i in range(20)] + [
        {"id": f"known-{i}", "timestamp": 1735689600} for i in range(20)
    ]

    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "u")
    monkeypatch.setattr(video_import, "get_user_liked_videos", lambda _u: feed_liked)
    monkeypatch.setattr(video_import, "get_user_saved_videos", lambda _u: feed_saved)

    video_import.import_from_tiktok()

    videos = crud.get_videos(sqlite_session)
    assert len(videos) == 61
    assert {v.id for v in videos if v.id.startswith("known-") and v.liked and v.saved} == {
        f"known-{i}" for i in range(20)
    }
    assert {v.id for v in videos if v.id.startswith("new-liked-") and v.liked and not v.saved} == {
        f"new-liked-{i}" for i in range(20)
    }
    assert {v.id for v in videos if v.id.startswith("new-saved-") and not v.liked and v.saved} == {
        f"new-saved-{i}" for i in range(20)
    }
