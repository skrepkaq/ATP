import json
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from atp import crud, video_import
from atp.models import Video, VideoInfo


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def make_ids(prefix: str, count: int, start: int = 1) -> list[str]:
    return [f"{prefix}{idx}" for idx in range(start, start + count)]


def make_db_rows(
    ids: list[str], *, liked: bool = False, saved: bool = False
) -> list[tuple[str, bool, bool]]:
    return [(video_id, liked, saved) for video_id in ids]


def seed_db_videos(sqlite_session: Session, videos: list[tuple[str, bool, bool]]) -> None:
    base_date = datetime(2025, 1, 1)
    rows = [
        Video(
            id=video_id,
            date=base_date + timedelta(seconds=idx),
            liked=liked,
            saved=saved,
        )
        for idx, (video_id, liked, saved) in enumerate(videos)
    ]
    sqlite_session.add_all(rows)
    sqlite_session.commit()


def make_importer(
    video_ids: list[str],
) -> tuple[Callable[[str], list[dict]], dict[str, int]]:
    stats = {"called": 0, "taken": 0}
    payload = [
        {"id": video_id, "timestamp": 1735689600 - index}
        for index, video_id in enumerate(video_ids)
    ]

    class CountingList(list[dict]):
        def __iter__(self):  # type: ignore[override]
            for item in super().__iter__():
                stats["taken"] += 1
                yield item

    def importer(_user: str) -> list[dict]:
        stats["called"] += 1
        return CountingList(payload)

    return importer, stats


def read_state(sqlite_session: Session) -> dict[str, tuple[bool, bool]]:
    return {v.id: (v.liked, v.saved) for v in crud.get_videos(sqlite_session)}


def assert_flags_for_ids(
    state: dict[str, tuple[bool, bool]], ids: list[str], expected: tuple[bool, bool]
) -> None:
    mismatched = {
        video_id: state.get(video_id) for video_id in ids if state.get(video_id) != expected
    }
    assert mismatched == {}


@pytest.mark.unit
def test_parse_tiktok_json_file_parses_and_sorts_and_deduplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "tiktok.json"
    _write_json(
        file,
        {
            "Activity": {
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
    monkeypatch.setattr(video_import, "DOWNLOAD_SAVED_VIDEOS", True)
    monkeypatch.setattr(video_import, "DOWNLOAD_LIKED_VIDEOS", True)

    result = video_import.parse_tiktok_json_file(str(file))

    assert result == [
        VideoInfo(id="2", date=datetime(2025, 1, 2, 10, 0, 0), liked=True, saved=False),
        VideoInfo(id="3", date=datetime(2025, 1, 3, 10, 0, 0), liked=False, saved=True),
        VideoInfo(id="4", date=datetime(2025, 1, 4, 10, 0, 0), liked=True, saved=True),
    ]


@pytest.mark.unit
def test_parse_tiktok_json_file_returns_none_on_invalid_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    file = tmp_path / "bad.json"
    _write_json(file, {"Your Activity": {}})
    monkeypatch.setattr(video_import, "DOWNLOAD_SAVED_VIDEOS", True)
    monkeypatch.setattr(video_import, "DOWNLOAD_LIKED_VIDEOS", True)

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
                        },
                        {
                            "date": "2025-01-02 10:00:00",
                            "link": "https://www.tiktok.com/@u/video/2/",
                        },
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
    monkeypatch.setattr(video_import, "DOWNLOAD_SAVED_VIDEOS", False)
    monkeypatch.setattr(video_import, "DOWNLOAD_LIKED_VIDEOS", True)

    result = video_import.parse_tiktok_json_file(str(file))

    assert result == [
        VideoInfo(id="2", date=datetime(2025, 1, 2, 10, 0, 0), liked=True, saved=False)
    ]


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
            VideoInfo(id="already", date=d_old),
            VideoInfo(id="fresh", date=d_new),
        ],
    )

    bulk_batches: list[list[VideoInfo]] = []

    def capture_bulk(_db: Session, videos: list[VideoInfo]) -> None:
        bulk_batches.append(videos)

    monkeypatch.setattr(video_import.crud, "add_videos_bulk", capture_bulk)

    video_import.import_from_file()

    assert bulk_batches == [[VideoInfo(id="fresh", date=d_new)]]


@pytest.mark.unit
def test_import_from_file_update_video_sources_bulk_when_existing_gains_like(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(
        Video(id="2", date=datetime(2025, 1, 1), liked=False, saved=False),
    )
    sqlite_session.commit()

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/fake/path.json")
    monkeypatch.setattr(video_import.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    d = datetime(2025, 2, 1, 12, 0, 0)
    parsed = [VideoInfo(id="2", date=d, liked=True, saved=False)]
    monkeypatch.setattr(video_import, "parse_tiktok_json_file", lambda _p: parsed)

    bulk_batches: list[list[VideoInfo]] = []
    update_batches: list[list[VideoInfo]] = []

    monkeypatch.setattr(
        video_import.crud,
        "add_videos_bulk",
        lambda _db, videos: bulk_batches.append(videos),
    )
    monkeypatch.setattr(
        video_import.crud,
        "update_video_sources_bulk",
        lambda _db, videos: update_batches.append(videos),
    )

    video_import.import_from_file()

    assert bulk_batches == []
    assert update_batches == [parsed]


@pytest.mark.unit
def test_import_from_file_update_video_sources_bulk_when_existing_gains_saved(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(
        Video(id="2", date=datetime(2025, 1, 1), liked=True, saved=False),
    )
    sqlite_session.commit()

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/fake/path.json")
    monkeypatch.setattr(video_import.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    d = datetime(2025, 2, 1, 12, 0, 0)
    parsed = [VideoInfo(id="2", date=d, liked=False, saved=True)]
    monkeypatch.setattr(video_import, "parse_tiktok_json_file", lambda _p: parsed)

    bulk_batches: list[list[VideoInfo]] = []
    update_batches: list[list[VideoInfo]] = []

    monkeypatch.setattr(
        video_import.crud,
        "add_videos_bulk",
        lambda _db, videos: bulk_batches.append(videos),
    )
    monkeypatch.setattr(
        video_import.crud,
        "update_video_sources_bulk",
        lambda _db, videos: update_batches.append(videos),
    )

    video_import.import_from_file()

    assert bulk_batches == []
    assert update_batches == [parsed]


@pytest.mark.unit
def test_import_from_file_mixed_add_and_update_video_sources(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(
        Video(id="old", date=datetime(2025, 1, 1), liked=False, saved=False),
    )
    sqlite_session.commit()

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/fake/path.json")
    monkeypatch.setattr(video_import.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    d_new = datetime(2025, 3, 1, 12, 0, 0)
    d_old = datetime(2025, 2, 1, 12, 0, 0)
    parsed = [
        VideoInfo(id="old", date=d_old, liked=True, saved=False),
        VideoInfo(id="fresh", date=d_new, liked=True, saved=False),
    ]
    monkeypatch.setattr(video_import, "parse_tiktok_json_file", lambda _p: parsed)

    bulk_batches: list[list[VideoInfo]] = []
    update_batches: list[list[VideoInfo]] = []

    monkeypatch.setattr(
        video_import.crud,
        "add_videos_bulk",
        lambda _db, videos: bulk_batches.append(videos),
    )
    monkeypatch.setattr(
        video_import.crud,
        "update_video_sources_bulk",
        lambda _db, videos: update_batches.append(videos),
    )

    video_import.import_from_file()

    assert bulk_batches == [[VideoInfo(id="fresh", date=d_new, liked=True, saved=False)]]
    assert update_batches == [[VideoInfo(id="old", date=d_old, liked=True, saved=False)]]


@pytest.mark.unit
def test_import_from_file_no_update_when_sources_already_match(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(
        Video(id="2", date=datetime(2025, 1, 1), liked=True, saved=True),
    )
    sqlite_session.commit()

    monkeypatch.setattr(video_import, "TIKTOK_DATA_FILE", "/fake/path.json")
    monkeypatch.setattr(video_import.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    d = datetime(2025, 2, 1, 12, 0, 0)
    parsed = [VideoInfo(id="2", date=d, liked=True, saved=True)]
    monkeypatch.setattr(video_import, "parse_tiktok_json_file", lambda _p: parsed)

    update_called = False

    def no_update(_db: Session, _videos: list[VideoInfo]) -> None:
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(video_import.crud, "update_video_sources_bulk", no_update)

    video_import.import_from_file()

    assert update_called is False


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
    sqlite_session.add(Video(id="known", date=datetime(2025, 1, 1), liked=True))
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
def test_import_from_tiktok_source_template_for_custom_db_and_importer(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_ids = make_ids("already-liked-", 120)
    new_liked_ids = make_ids("new-liked-", 80)

    seed_db_videos(
        sqlite_session,
        make_db_rows(already_liked_ids, liked=True, saved=False)
        + [
            ("existing-not-liked", False, True),
            ("untouched", False, False),
        ],
    )

    importer, importer_stats = make_importer(
        new_liked_ids + ["existing-not-liked"] + make_ids("already-liked-", 10)
    )
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="liked")

    state = read_state(sqlite_session)
    assert len(state) == 120 + 2 + 80
    assert importer_stats["called"] == 1
    assert importer_stats["taken"] == 80 + 1 + 10
    assert_flags_for_ids(state, already_liked_ids, (True, False))
    assert_flags_for_ids(state, new_liked_ids, (True, False))
    assert state["existing-not-liked"] == (True, True)
    assert state["untouched"] == (False, False)


@pytest.mark.unit
def test_import_from_tiktok_normal_notalot_of_likes(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_ids = make_ids("already-liked-", 20)
    new_liked_ids = make_ids("new-liked-", 10)

    seed_db_videos(
        sqlite_session,
        make_db_rows(already_liked_ids, liked=True, saved=False)
        + [
            ("saved", False, True),
        ],
    )

    importer, importer_stats = make_importer(new_liked_ids + already_liked_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="liked")

    state = read_state(sqlite_session)
    assert len(state) == 20 + 1 + 10  # 20 liked + 1 saved + 10 new liked
    assert_flags_for_ids(state, already_liked_ids, (True, False))
    assert_flags_for_ids(state, new_liked_ids, (True, False))
    assert state["saved"] == (False, True)
    assert importer_stats["taken"] == 10 + 10  # 10 new liked + 10 already liked


@pytest.mark.unit
def test_import_from_tiktok_normal_not_a_lot_of_likes(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_ids = make_ids("already-liked-", 5)
    new_liked_ids = make_ids("new-liked-", 2)

    seed_db_videos(sqlite_session, make_db_rows(already_liked_ids, liked=True, saved=False))

    importer, importer_stats = make_importer(new_liked_ids + already_liked_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="liked")

    state = read_state(sqlite_session)
    assert len(state) == 5 + 2  # 5 liked + 2 new liked
    assert_flags_for_ids(state, already_liked_ids, (True, False))
    assert_flags_for_ids(state, new_liked_ids, (True, False))
    assert importer_stats["taken"] == 2 + 5  # 2 new liked + 5 already liked


@pytest.mark.unit
def test_import_from_tiktok_no_liked(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_saved_ids = make_ids("already-saved-", 20)
    new_liked_ids = make_ids("new-liked-", 10)

    seed_db_videos(sqlite_session, make_db_rows(already_saved_ids, liked=False, saved=True))

    importer, importer_stats = make_importer(new_liked_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="liked")

    state = read_state(sqlite_session)
    assert len(state) == 20  # 20 already saved
    assert_flags_for_ids(state, already_saved_ids, (False, True))
    assert importer_stats["taken"] == 0
    assert importer_stats["called"] == 0


@pytest.mark.unit
def test_import_from_tiktok_no_saved(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_ids = make_ids("already-liked-", 20)
    new_saved_ids = make_ids("new-saved-", 10)

    seed_db_videos(sqlite_session, make_db_rows(already_liked_ids, saved=False, liked=True))

    importer, importer_stats = make_importer(new_saved_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="saved")

    state = read_state(sqlite_session)
    assert len(state) == 20  # 20 already liked
    assert_flags_for_ids(state, already_liked_ids, (True, False))
    assert importer_stats["taken"] == 0
    assert importer_stats["called"] == 0


@pytest.mark.unit
def test_import_from_tiktok_saved_happy_path(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_saved_ids = make_ids("already-saved-", 20)
    existing_not_saved_ids = make_ids("existing-not-saved-", 12)
    new_saved_ids = make_ids("new-saved-", 15)

    seed_db_videos(
        sqlite_session,
        make_db_rows(already_saved_ids, liked=False, saved=True)
        + make_db_rows(existing_not_saved_ids, liked=True, saved=False)
        + [("untouched-liked-only", True, False)],
    )

    importer_ids = new_saved_ids + existing_not_saved_ids[:6] + already_saved_ids[:10]
    importer, importer_stats = make_importer(importer_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="saved")

    state = read_state(sqlite_session)
    assert len(state) == 20 + 12 + 1 + 15
    assert importer_stats["called"] == 1
    assert importer_stats["taken"] == 15 + 6 + 10
    assert_flags_for_ids(state, already_saved_ids, (False, True))
    assert_flags_for_ids(state, new_saved_ids, (False, True))
    assert_flags_for_ids(state, existing_not_saved_ids[:6], (True, True))
    assert_flags_for_ids(state, existing_not_saved_ids[6:], (True, False))
    assert state["untouched-liked-only"] == (True, False)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("prefix_len", "new_id", "expect_new_in_state"),
    [
        (9, "new-after-9", True),
        (10, "new-after-10", False),
    ],
)
def test_import_from_tiktok_same_source_stop_threshold(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    prefix_len: int,
    new_id: str,
    expect_new_in_state: bool,
) -> None:
    already_liked_ids = make_ids("already-liked-", 20)
    seed_db_videos(sqlite_session, make_db_rows(already_liked_ids, liked=True, saved=False))
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    importer, stats = make_importer(already_liked_ids[:prefix_len] + [new_id])
    video_import.import_from_tiktok_source(importer=importer, source="liked")
    state = read_state(sqlite_session)
    if expect_new_in_state:
        assert state[new_id] == (True, False)
    else:
        assert new_id not in state
    assert stats["taken"] == 10


@pytest.mark.unit
@pytest.mark.parametrize(
    ("prefix_len", "new_id", "expect_new_in_state"),
    [
        (99, "new-after-99", True),
        (100, "new-after-100", False),
    ],
)
def test_import_from_tiktok_existing_stop_threshold(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    prefix_len: int,
    new_id: str,
    expect_new_in_state: bool,
) -> None:
    keep_alive_saved = "already-saved-with-source"
    existing_not_saved_ids = make_ids("existing-not-saved-", 130)
    seed_db_videos(
        sqlite_session,
        [(keep_alive_saved, False, True)]
        + make_db_rows(existing_not_saved_ids, liked=True, saved=False),
    )
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    importer, stats = make_importer(existing_not_saved_ids[:prefix_len] + [new_id])
    video_import.import_from_tiktok_source(importer=importer, source="saved")
    state = read_state(sqlite_session)
    if expect_new_in_state:
        assert state[new_id] == (False, True)
    else:
        assert new_id not in state
    assert stats["taken"] == 100


@pytest.mark.unit
def test_import_from_tiktok_no_source(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_no_source_ids = make_ids("already-liked-", 110)
    new_liked_ids = make_ids("new-liked-", 10)

    seed_db_videos(
        sqlite_session,
        [("already-liked-with-source", True, False)]
        + make_db_rows(already_liked_no_source_ids, liked=False, saved=False),
    )

    importer, importer_stats = make_importer(new_liked_ids + already_liked_no_source_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="liked")

    state = read_state(sqlite_session)
    assert len(state) == 1 + 110 + 10  # 1 already liked + 110 already liked + 10 new liked
    assert_flags_for_ids(state, already_liked_no_source_ids[:100], (True, False))
    assert_flags_for_ids(state, already_liked_no_source_ids[100:110], (False, False))
    assert_flags_for_ids(state, new_liked_ids, (True, False))
    assert importer_stats["taken"] == 10 + 100  # 10 new liked + 100 already liked (update sources)


@pytest.mark.unit
def test_import_from_tiktok_no_source_no_new(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_no_source_ids = make_ids("already-liked-", 110)

    seed_db_videos(
        sqlite_session,
        [("already-liked-with-source", True, False)]
        + make_db_rows(already_liked_no_source_ids, liked=False, saved=False),
    )

    importer, importer_stats = make_importer(already_liked_no_source_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")
    video_import.import_from_tiktok_source(importer=importer, source="liked")
    state = read_state(sqlite_session)
    assert len(state) == 1 + 110  # 1 already liked + 110 already liked
    assert_flags_for_ids(state, already_liked_no_source_ids[:100], (True, False))
    assert_flags_for_ids(state, already_liked_no_source_ids[100:110], (False, False))
    assert importer_stats["taken"] == 100  # 100 already liked (update sources)


@pytest.mark.unit
def test_import_from_tiktok_no_new(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    already_liked_ids = make_ids("already-liked-", 20)

    seed_db_videos(sqlite_session, make_db_rows(already_liked_ids, liked=True, saved=False))

    importer, importer_stats = make_importer(already_liked_ids)
    monkeypatch.setattr(video_import, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(video_import, "TIKTOK_USER", "template-user")

    video_import.import_from_tiktok_source(importer=importer, source="liked")

    state = read_state(sqlite_session)
    assert len(state) == 20  # 20 already liked
    assert_flags_for_ids(state, already_liked_ids, (True, False))
    assert importer_stats["taken"] == 10  # 10 already liked


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
