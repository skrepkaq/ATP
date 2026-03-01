from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from atp import check_availability, crud, settings
from atp.models import Video, VideoStatus


@pytest.mark.integration
def test_handle_unavailable_splits_large_video_and_marks_deleted(
    sqlite_session: Session,
    downloads_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    video = Video(id="big", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS, name="name")
    sqlite_session.add(video)
    sqlite_session.commit()

    video_file = downloads_dir / "big.mp4"
    video_file.write_bytes(b"x" * int(1.5 * 1024 * 1024))

    monkeypatch.setattr(settings, "DOWNLOADS_DIR", str(downloads_dir))
    monkeypatch.setattr(settings, "TELEGRAM_MAX_VIDEO_SIZE", 1024 * 1024)
    monkeypatch.setattr(check_availability, "split_video", lambda *_args, **_kwargs: [video_file])
    monkeypatch.setattr(check_availability, "_send_multipart_video", lambda *_args, **_kwargs: 42)
    monkeypatch.setattr(check_availability, "temp_files_cleanup", lambda: None)

    check_availability._handle_unavailable(sqlite_session, video)

    refreshed = crud.get_videos(sqlite_session, [VideoStatus.DELETED])[0]
    assert refreshed.message_id == 42
    assert refreshed.status == VideoStatus.DELETED


@pytest.mark.integration
def test_check_video_batch_handles_unavailable_and_restored(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add_all(
        [
            Video(id="to_delete", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS),
            Video(
                id="to_restore",
                date=datetime(2025, 1, 1),
                status=VideoStatus.DELETED,
                message_id=10,
            ),
        ]
    )
    sqlite_session.commit()

    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(check_availability, "CHECK_INTERVAL_DAYS", 0.01)
    unavailable_calls: list[str] = []
    restored_calls: list[str] = []
    monkeypatch.setattr(
        check_availability,
        "_handle_unavailable",
        lambda _db, video: unavailable_calls.append(video.id),
    )
    monkeypatch.setattr(
        check_availability,
        "_handle_restored",
        lambda _db, video: restored_calls.append(video.id),
    )

    def fake_check(video_id: str):
        if video_id == "to_delete":
            return SimpleNamespace(deleted_reason="not found")
        return SimpleNamespace(deleted_reason=None)

    monkeypatch.setattr(check_availability, "check_video_availability", fake_check)

    check_availability.check_video_batch()

    assert unavailable_calls == ["to_delete"]
    assert restored_calls == ["to_restore"]


@pytest.mark.integration
def test_check_video_batch_no_videos_logs_and_returns(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    called = {"checked": False}
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda _id: called.__setitem__("checked", True),
    )
    check_availability.check_video_batch()
    assert called["checked"] is False


@pytest.mark.integration
def test_check_video_batch_selects_least_recently_checked_first(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The batch must select videos by last_checked ASC (NULLs first) every hour.

    Setup: 48 SUCCESS videos total.
      - 2 videos were never checked (NULL last_checked): never_a, never_b
      - 46 videos were checked recently

    With CHECK_INTERVAL_DAYS=1, batch_size is ceil(48 / 1 / 24) == 2.
    Running 48 hourly cycles (2 full days) should check each video exactly twice.
    """
    now = datetime(2025, 6, 1, 12, 0, 0)
    videos = [
        Video(
            id=f"recent_{i:02d}",
            date=datetime(2025, 1, 1),
            status=VideoStatus.SUCCESS,
            last_checked=now - timedelta(minutes=i + 1),
        )
        for i in range(46)
    ]
    videos += [
        Video(
            id="never_a", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS, last_checked=None
        ),
        Video(
            id="never_b", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS, last_checked=None
        ),
    ]
    sqlite_session.add_all(videos)
    sqlite_session.commit()

    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(check_availability, "CHECK_INTERVAL_DAYS", 1)
    monkeypatch.setattr(
        check_availability,
        "check_video_availability",
        lambda _id: SimpleNamespace(deleted_reason=None),
    )

    checked_ids: list[str] = []
    current_time = {"value": now}

    class FakeDateTime:
        @classmethod
        def now(cls) -> datetime:
            return current_time["value"]

    monkeypatch.setattr(crud, "datetime", FakeDateTime)

    original_update = crud.update_video

    def recording_update(db, video, **kwargs):
        checked_ids.append(video.id)
        return original_update(db, video, **kwargs)

    monkeypatch.setattr(check_availability.crud, "update_video", recording_update)

    check_counts: dict[str, int] = {video.id: 0 for video in videos}

    cycle = 0
    for day in range(2):
        day_checked: set[str] = set()
        for hour in range(24):
            current_time["value"] = now + timedelta(days=day, hours=hour)
            checked_ids.clear()

            check_availability.check_video_batch()

            assert len(checked_ids) == 2, "Each hourly cycle must check exactly 2 videos."
            assert len(set(checked_ids)) == 2, "Each cycle must contain two distinct videos."
            if hour == 0:
                assert set(checked_ids) == {"never_a", "never_b"}, (
                    "At the start of each daily cycle, NULL last_checked videos must be first."
                )
            else:
                first_recent_idx = 47 - 2 * hour
                second_recent_idx = 46 - 2 * hour
                assert set(checked_ids) == {
                    f"recent_{first_recent_idx:02d}",
                    f"recent_{second_recent_idx:02d}",
                }, (
                    "Expected exact recent_* pair for this hour based on "
                    "least-recently-checked ordering."
                )
            for video_id in checked_ids:
                assert video_id not in day_checked, (
                    f"Video {video_id} was checked twice in day={day}, "
                    "but each video must be checked once per 24-hour cycle."
                )
                day_checked.add(video_id)
                check_counts[video_id] += 1
            cycle += 1
        assert len(day_checked) == 48, "Each 24-hour cycle must check all 48 videos exactly once."

    assert cycle == 48, "Test must run exactly 48 hourly cycles."
    assert check_counts["never_a"] == 2
    assert check_counts["never_b"] == 2
    assert all(count == 2 for count in check_counts.values()), (
        "Across 48 cycles, every video must be checked exactly twice."
    )


@pytest.mark.integration
def test_check_video_batch_skips_on_network_none(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sqlite_session.add(Video(id="n1", date=datetime(2025, 1, 1), status=VideoStatus.SUCCESS))
    sqlite_session.commit()
    monkeypatch.setattr(check_availability, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(check_availability, "CHECK_INTERVAL_DAYS", 0.01)
    monkeypatch.setattr(check_availability, "check_video_availability", lambda _id: None)
    calls = {"unavailable": False}
    monkeypatch.setattr(
        check_availability,
        "_handle_unavailable",
        lambda *_args, **_kwargs: calls.__setitem__("unavailable", True),
    )
    check_availability.check_video_batch()
    assert calls["unavailable"] is False
