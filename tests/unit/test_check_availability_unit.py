import io
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from atp import check_availability, crud, settings
from atp.models import Video, VideoStatus


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

    check_availability._handle_unavailable(sqlite_session, video)

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

    check_availability._handle_unavailable(sqlite_session, video)

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

    check_availability._handle_unavailable(sqlite_session, video)

    refreshed = crud.get_videos(sqlite_session)[0]
    assert refreshed.status == VideoStatus.SUCCESS


@pytest.mark.unit
def test_handle_restored_without_message_id_updates_status(sqlite_session: Session) -> None:
    video = Video(id="r1", date=datetime(2025, 1, 1), status=VideoStatus.DELETED, message_id=None)
    sqlite_session.add(video)
    sqlite_session.commit()

    check_availability._handle_restored(sqlite_session, video)

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

    check_availability._handle_restored(sqlite_session, video)

    refreshed = crud.get_videos(sqlite_session, [VideoStatus.DELETED])[0]
    assert refreshed.message_id == 10
