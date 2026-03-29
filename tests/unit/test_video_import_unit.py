import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from atp import crud, video_import
from atp.models import Video


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.unit
def test_parse_tiktok_json_file_parses_and_sorts_and_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "tiktok.json"
    _write_json(
        file,
        {
            "Your Activity": {
                "Favorite Videos": {
                    "FavoriteVideoList": [
                        {
                            "Date": "2025-01-03 10:00:00",
                            "Link": "https://www.tiktok.com/@u/video/3/",
                        },
                        {
                            "date": "2025-01-04 10:00:00",
                            "link": "https://www.tiktok.com/@u/video/4/",
                        },
                    ]
                },
                "Like List": {
                    "ItemFavoriteList": [
                        {
                            "date": "2025-01-02 10:00:00",
                            "link": "https://www.tiktok.com/@u/video/2/",
                        },
                        {
                            "date": "2025-01-02 10:00:00",
                            "link": "https://www.tiktok.com/@u/video/2/",
                        },
                        {
                            "date": "2025-01-04 10:00:00",
                            "link": "https://www.tiktok.com/@u/video/4/",
                        },
                    ]
                },
            }
        },
    )
    monkeypatch.setattr(video_import, "IMPORT_FAVORITE_VIDEOS", True)
    monkeypatch.setattr(video_import, "IMPORT_LIKED_VIDEOS", True)

    result = video_import.parse_tiktok_json_file(str(file))

    assert result == [
        {"id": "2", "date": datetime(2025, 1, 2, 10, 0, 0)},
        {"id": "3", "date": datetime(2025, 1, 3, 10, 0, 0)},
        {"id": "4", "date": datetime(2025, 1, 4, 10, 0, 0)},
    ]


@pytest.mark.unit
def test_parse_tiktok_json_file_returns_none_on_invalid_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "bad.json"
    _write_json(file, {"Your Activity": {}})
    monkeypatch.setattr(video_import, "IMPORT_FAVORITE_VIDEOS", True)
    monkeypatch.setattr(video_import, "IMPORT_LIKED_VIDEOS", True)

    assert video_import.parse_tiktok_json_file(str(file)) is None


@pytest.mark.unit
def test_parse_tiktok_json_file_respects_import_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "flags.json"
    _write_json(
        file,
        {
            "Likes and Favorites": {
                "Favorite Videos": {
                    "FavoriteVideoList": [
                        {
                            "Date": "2025-01-03 10:00:00",
                            "Link": "https://www.tiktok.com/@u/video/3/",
                        }
                    ]
                },
                "Like List": {
                    "ItemFavoriteList": [
                        {
                            "date": "2025-01-02 10:00:00",
                            "link": "https://www.tiktok.com/@u/video/2/",
                        }
                    ]
                },
            }
        },
    )
    monkeypatch.setattr(video_import, "IMPORT_FAVORITE_VIDEOS", False)
    monkeypatch.setattr(video_import, "IMPORT_LIKED_VIDEOS", True)

    result = video_import.parse_tiktok_json_file(str(file))

    assert result == [{"id": "2", "date": datetime(2025, 1, 2, 10, 0, 0)}]


@pytest.mark.unit
def test_import_from_file_returns_when_source_missing(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/no/such/file.json")

    called = []
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import.crud, "get_videos", lambda _db: [])
    monkeypatch.setattr(video_import, "parse_tiktok_json_file", lambda _p: called.append("parse"))
    monkeypatch.setattr(
        video_import.crud, "add_videos_bulk", lambda _db, _videos: called.append("bulk")
    )

    video_import.import_from_file()

    assert called == []


@pytest.mark.unit
def test_import_from_file_returns_when_parser_returns_no_videos(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/tmp/ok.json")
    monkeypatch.setattr(video_import.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "parse_tiktok_json_file", lambda _p: [])
    called = {"bulk": False}
    monkeypatch.setattr(
        video_import.crud,
        "add_videos_bulk",
        lambda *_args, **_kwargs: called.__setitem__("bulk", True),
    )

    video_import.import_from_file()
    assert called["bulk"] is False


@pytest.mark.unit
def test_import_from_file_add_videos_bulk_only_new_ids(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(Video(id="already", date=datetime(2025, 1, 1)))
    sqlite_session.commit()

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/fake/path.json")
    monkeypatch.setattr(video_import.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    d_new = datetime(2025, 2, 1, 12, 0, 0)
    d_old = datetime(2025, 1, 15, 12, 0, 0)
    monkeypatch.setattr(
        video_import,
        "parse_tiktok_json_file",
        lambda _p: [
            {"id": "already", "date": d_old},
            {"id": "fresh", "date": d_new},
        ],
    )

    bulk_batches: list[list[dict]] = []

    def capture_bulk(_db: Session, videos: list[dict]) -> None:
        bulk_batches.append(videos)

    monkeypatch.setattr(video_import.crud, "add_videos_bulk", capture_bulk)

    video_import.import_from_file()

    assert bulk_batches == [[{"id": "fresh", "date": d_new}]]


@pytest.mark.unit
def test_import_from_tiktok_returns_when_db_empty(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    called = {"liked": False}
    monkeypatch.setattr(
        video_import,
        "get_user_liked_videos",
        lambda _u: called.__setitem__("liked", True),
    )
    video_import.import_from_tiktok()
    assert called["liked"] is False


@pytest.mark.unit
def test_import_from_tiktok_adds_new_videos(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(Video(id="known", date=datetime(2025, 1, 1)))
    sqlite_session.commit()
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "u")
    monkeypatch.setattr(
        video_import,
        "get_user_liked_videos",
        lambda _u: [
            {"id": "known", "timestamp": 1},
            {"id": "new1", "timestamp": 1735689600},
        ],
    )

    video_import.import_from_tiktok()
    ids = {v.id for v in crud.get_videos(sqlite_session)}
    assert ids == {"known", "new1"}


@pytest.mark.unit
def test_import_from_tiktok_handles_provider_exception(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(Video(id="known", date=datetime(2025, 1, 1)))
    sqlite_session.commit()
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "u")
    monkeypatch.setattr(
        video_import,
        "get_user_liked_videos",
        lambda _u: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    video_import.import_from_tiktok()


@pytest.mark.integration
def test_deprecated_run_imports_from_file(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr("time.sleep", lambda _s: None)
    monkeypatch.setattr(video_import, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(video_import, "import_from_file", lambda: called.append("from_file"))
    monkeypatch.setattr(video_import, "download_new_videos", lambda: called.append("download"))
    video_import.deprecated_run()

    assert called == ["migrations", "from_file", "download"]
