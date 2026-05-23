import io
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from atp import check_availability, crud, settings
from atp.models import Video, VideoInfo, VideoStatus


@pytest.mark.unit
def test_get_caption_truncates_to_telegram_limit() -> None:
    video = Video(
        id="v1",
        author="author",
        name="x" * 2000,
        date=datetime(2025, 1, 1),
    )

    caption = check_availability._get_caption(video)

    assert len(caption) == 1024
    assert caption.endswith("01.01.2025")


@pytest.mark.unit
def test_get_caption_keeps_text_when_exactly_at_limit() -> None:
    author = "a" * 100
    # 1024 - (len(author + "\n") + len("\n01.01.2025")) = 912
    name = "x" * 912
    video = Video(
        id="v2",
        author=author,
        name=name,
        date=datetime(2025, 1, 1),
    )

    caption = check_availability._get_caption(video)

    assert len(caption) == 1024
    assert not caption.split("\n")[1].endswith("...")
    assert caption.endswith("01.01.2025")


@pytest.mark.unit
def test_get_caption_adds_ellipsis_when_name_is_too_long() -> None:
    author = "author"
    # Allowed name length with this author is 1006, make it 1 char longer.
    name = "x" * 1007
    video = Video(
        id="v3",
        author=author,
        name=name,
        date=datetime(2025, 1, 1),
    )

    caption = check_availability._get_caption(video)

    content, _, date = caption.rpartition("\n")
    assert len(caption) == 1024
    assert content.endswith("...")
    assert date == "01.01.2025"


@pytest.mark.unit
def test_send_multipart_video_returns_first_message_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    part1 = tmp_path / "p1.mp4"
    part2 = tmp_path / "p2.mp4"
    part1.write_bytes(b"v1")
    part2.write_bytes(b"v2")

    monkeypatch.setattr(check_availability, "generate_bmp", lambda _seed: object())
    monkeypatch.setattr(
        check_availability,
        "send_media",
        lambda caption, photos=None, video=None: [  # noqa: ARG005
            {"message_id": 10},
            {"message_id": 11},
        ],
    )
    monkeypatch.setattr(check_availability, "edit_media", lambda **_kwargs: True)
    monkeypatch.setattr(check_availability.time, "sleep", lambda _s: None)

    msg_id = check_availability._send_multipart_video([part1, part2], "cap")

    assert msg_id == 10


@pytest.mark.unit
def test_handle_unavailable_returns_when_video_file_missing(
    sqlite_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = Video(id="missing", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS)
    sqlite_session.add(video)
    sqlite_session.commit()
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(tmp_path))

    ok = check_availability._handle_unavailable(sqlite_session, video)
    assert ok is False

    refreshed = crud.get_videos(sqlite_session)[0]
    assert refreshed.status == VideoStatus.SUCCESS


@pytest.mark.unit
def test_handle_unavailable_sends_single_video_path(
    sqlite_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = Video(id="small", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS, name="n")
    sqlite_session.add(video)
    sqlite_session.commit()
    (tmp_path / "small.mp4").write_bytes(b"x" * 10)
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TELEGRAM_MAX_VIDEO_SIZE", 1024)
    monkeypatch.setattr(check_availability, "get_file_size", lambda _p: 10)
    monkeypatch.setattr(
        check_availability,
        "send_media",
        lambda caption, video=None, photos=None: {"message_id": 123},  # noqa: ARG005
    )
    monkeypatch.setattr(check_availability, "temp_files_cleanup", lambda: None)

    ok = check_availability._handle_unavailable(sqlite_session, video)
    assert ok is True

    refreshed = crud.get_videos(sqlite_session, [VideoStatus.DELETED])[0]
    assert refreshed.message_id == 123


@pytest.mark.unit
def test_handle_unavailable_returns_when_split_fails(
    sqlite_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = Video(id="big2", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS, name="n")
    sqlite_session.add(video)
    sqlite_session.commit()
    (tmp_path / "big2.mp4").write_bytes(b"x")
    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "TELEGRAM_MAX_VIDEO_SIZE", 1)
    monkeypatch.setattr(check_availability, "get_file_size", lambda _p: 1000)
    monkeypatch.setattr(check_availability, "split_video", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(check_availability, "temp_files_cleanup", lambda: None)

    ok = check_availability._handle_unavailable(sqlite_session, video)
    assert ok is False

    refreshed = crud.get_videos(sqlite_session)[0]
    assert refreshed.status == VideoStatus.SUCCESS


@pytest.mark.unit
def test_handle_restored_without_message_id_updates_status(sqlite_session: Session) -> None:
    video = Video(id="r1", date=datetime(2025, 1, 1), status=VideoStatus.DELETED, message_id=None)
    sqlite_session.add(video)
    sqlite_session.commit()

    ok = check_availability._handle_restored(sqlite_session, video)
    assert ok is True

    refreshed = crud.get_videos(sqlite_session, [VideoStatus.SUCCESS])[0]
    assert refreshed.message_id is None


@pytest.mark.unit
def test_handle_restored_with_failed_edit_keeps_deleted(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    video = Video(id="r2", date=datetime(2025, 1, 1), status=VideoStatus.DELETED, message_id=10)
    sqlite_session.add(video)
    sqlite_session.commit()
    monkeypatch.setattr(check_availability, "generate_bmp", lambda _id: io.BytesIO(b"x"))
    monkeypatch.setattr(check_availability, "edit_media", lambda **kwargs: False)  # noqa: ARG005

    ok = check_availability._handle_restored(sqlite_session, video)
    assert ok is False

    refreshed = crud.get_videos(sqlite_session, [VideoStatus.DELETED])[0]
    assert refreshed.message_id == 10


@pytest.mark.unit
def test_check_services_availability_skipped_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", False)
    called = {"check": False}
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda *_args, **_kwargs: called.__setitem__("check", True),
    )
    assert check_availability.check_services_availability() is True
    assert called["check"] is False


@pytest.mark.unit
def test_check_services_availability_returns_true_when_video_available(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda _video, no_errors=False: VideoInfo(  # noqa: ARG005
            deleted_reason=None,
            date=datetime(2023, 1, 1),
        ),
    )
    sqlite_session.add(
        Video(id="ok", date=datetime(2023, 1, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.commit()

    assert check_availability.check_services_availability() is True


@pytest.mark.unit
def test_check_services_availability_returns_false_when_all_unavailable(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda *_args, **_kwargs: None,
    )
    telegram_called = {"get": False}
    monkeypatch.setattr(
        check_availability.requests,
        "get",
        lambda *_args, **_kwargs: telegram_called.__setitem__("get", True),  # noqa: ARG005
    )
    sqlite_session.add(
        Video(id="old", date=datetime(2020, 1, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.commit()

    assert check_availability.check_services_availability() is False
    assert telegram_called["get"] is True


def _patch_deterministic_random_sample(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use population order so `check_services_availability` checks IDs predictably."""

    def fake_sample(population: list, k: int) -> list:
        pop = list(population)
        if not pop:
            return []
        return pop[:k]

    monkeypatch.setattr(check_availability.random, "sample", fake_sample)


@pytest.mark.unit
def test_check_services_availability_returns_true_when_only_later_video_available(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    _patch_deterministic_random_sample(monkeypatch)
    sqlite_session.add(
        Video(id="db-a", date=datetime(2023, 6, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.add(
        Video(id="db-b", date=datetime(2023, 7, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.commit()

    attempts = {"n": 0}

    def mock_check(_video: Video, no_errors: bool = False) -> VideoInfo | None:  # noqa: ARG001
        attempts["n"] += 1
        if attempts["n"] < 3:
            return None
        return VideoInfo(deleted_reason=None, date=datetime(2023, 1, 1))

    monkeypatch.setattr(check_availability, "check_video_availability", mock_check)

    assert check_availability.check_services_availability() is True
    assert attempts["n"] == 3


@pytest.mark.unit
def test_check_services_availability_returns_false_when_video_marked_deleted(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TikTok responds but video is gone (deleted_reason set) — still treated as unavailable."""
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    _patch_deterministic_random_sample(monkeypatch)
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda *_a, **_k: VideoInfo(  # noqa: ARG005
            deleted_reason="removed by user",
            date=datetime(2023, 1, 1),
        ),
    )
    telegram_called = {"get": False}
    monkeypatch.setattr(
        check_availability.requests,
        "get",
        lambda *_args, **_kwargs: telegram_called.__setitem__("get", True),  # noqa: ARG005
    )
    sqlite_session.add(
        Video(id="x1", date=datetime(2023, 1, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.commit()

    assert check_availability.check_services_availability() is False
    assert telegram_called["get"] is True


@pytest.mark.unit
def test_check_services_availability_returns_false_when_result_date_on_cutoff(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cutoff is exclusive: date must be strictly after 2022-03-01."""
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    _patch_deterministic_random_sample(monkeypatch)
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda *_a, **_k: VideoInfo(deleted_reason=None, date=datetime(2022, 3, 1)),  # noqa: ARG005
    )
    telegram_called = {"get": False}
    monkeypatch.setattr(
        check_availability.requests,
        "get",
        lambda *_args, **_kwargs: telegram_called.__setitem__("get", True),  # noqa: ARG005
    )
    sqlite_session.add(
        Video(id="edge", date=datetime(2023, 1, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.commit()

    assert check_availability.check_services_availability() is False
    assert telegram_called["get"] is True


@pytest.mark.unit
def test_check_services_availability_returns_false_when_telegram_probe_raises(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda *_a, **_k: None,  # noqa: ARG005
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ConnectionError("no route")

    monkeypatch.setattr(check_availability.requests, "get", boom)

    assert check_availability.check_services_availability() is False


@pytest.mark.unit
def test_check_services_availability_skips_db_videos_before_2022_cutoff(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Videos on or before 2022-03-01 are excluded from the sample pool."""
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    _patch_deterministic_random_sample(monkeypatch)
    checked_ids: list[str | int] = []

    def mock_check(video: Video, no_errors: bool = False) -> VideoInfo | None:  # noqa: ARG001
        checked_ids.append(video.id)
        return None

    monkeypatch.setattr(check_availability, "check_video_availability", mock_check)
    sqlite_session.add(
        Video(id="too-old", date=datetime(2022, 3, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.add(
        Video(id="fresh", date=datetime(2023, 1, 1), status=VideoStatus.SUCCESS),
    )
    sqlite_session.commit()

    assert check_availability.check_services_availability() is False
    assert "too-old" not in checked_ids
    assert "fresh" in checked_ids


@pytest.mark.unit
def test_check_services_availability_returns_false_with_empty_db_and_all_checks_fail(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No SUCCESS rows: only KNOWN_GOOD_TIKTOKS are probed; still returns False if all fail."""
    monkeypatch.setattr(settings, "CHECK_TIKTOK_AVAILABILITY", True)
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(settings, "KNOWN_GOOD_TIKTOKS", list(range(20)))
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda *_a, **_k: None,  # noqa: ARG005
    )
    telegram_called = {"get": False}
    monkeypatch.setattr(
        check_availability.requests,
        "get",
        lambda *_args, **_kwargs: telegram_called.__setitem__("get", True),  # noqa: ARG005
    )
    sqlite_session.commit()

    assert check_availability.check_services_availability() is False
    assert telegram_called["get"] is True


@pytest.mark.unit
def test_check_video_batch_returns_when_services_unavailable(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(Video(id="v1", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS))
    sqlite_session.commit()
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(check_availability, "check_services_availability", lambda: False)
    called = {"check": False}
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda _video: called.__setitem__("check", True),
    )

    check_availability.check_video_batch()

    assert called["check"] is False
