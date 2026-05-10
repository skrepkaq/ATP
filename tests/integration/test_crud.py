from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from atp import crud
from atp.models import VideoInfo, VideoStatus


@pytest.mark.integration
def test_add_video_to_db_is_idempotent(sqlite_session: Session) -> None:
    date = datetime(2025, 1, 1)
    v1 = crud.add_video_to_db(sqlite_session, "abc", date)
    v2 = crud.add_video_to_db(sqlite_session, "abc", date)

    assert v1.id == "abc"
    assert v2.id == "abc"
    assert len(crud.get_videos(sqlite_session)) == 1


@pytest.mark.integration
def test_add_videos_bulk_skips_existing(sqlite_session: Session) -> None:
    crud.add_video_to_db(sqlite_session, "existing", datetime(2025, 1, 1), liked=True, saved=False)
    crud.add_videos_bulk(
        sqlite_session,
        [
            VideoInfo(id="existing", date=datetime(2025, 1, 1), liked=False, saved=False),
            VideoInfo(id="new", date=datetime(2025, 1, 2), liked=False, saved=True),
        ],
    )

    videos = crud.get_videos(sqlite_session)
    assert len(videos) == 2
    assert videos[0].id == "existing"
    assert videos[0].liked
    assert not videos[0].saved
    assert videos[1].id == "new"
    assert not videos[1].liked
    assert videos[1].saved


@pytest.mark.integration
def test_update_video_sources_bulk_sets_liked_and_saved(sqlite_session: Session) -> None:
    crud.add_video_to_db(sqlite_session, "a", datetime(2025, 1, 1), liked=False, saved=False)
    crud.add_video_to_db(sqlite_session, "b", datetime(2025, 1, 2), liked=True, saved=False)
    crud.add_video_to_db(sqlite_session, "c", datetime(2025, 1, 3), liked=False, saved=True)
    crud.add_video_to_db(sqlite_session, "d", datetime(2025, 1, 4), liked=False, saved=False)

    crud.update_video_sources_bulk(
        sqlite_session,
        [
            VideoInfo(id="a", date=datetime(2025, 1, 1), liked=True, saved=True),
            VideoInfo(id="b", date=datetime(2025, 1, 2), liked=False, saved=True),
            VideoInfo(id="c", date=datetime(2025, 1, 3), liked=True, saved=False),
            VideoInfo(id="missing", date=datetime(2025, 1, 1), liked=True, saved=True),
            VideoInfo(id="d", date=datetime(2025, 1, 4), liked=False, saved=False),
        ],
    )

    by_id = {v.id: v for v in crud.get_videos(sqlite_session)}
    assert by_id["a"].liked and by_id["a"].saved
    assert by_id["b"].liked and by_id["b"].saved
    assert by_id["c"].liked and by_id["c"].saved
    assert not by_id["d"].liked and not by_id["d"].saved
    assert "missing" not in by_id


@pytest.mark.integration
def test_update_video_updates_fields_and_last_checked(sqlite_session: Session) -> None:
    video = crud.add_video_to_db(sqlite_session, "v1", datetime(2025, 1, 1))

    crud.update_video(
        sqlite_session,
        video=video,
        status=VideoStatus.SUCCESS,
        name="name",
        deleted_reason="reason",
    )

    updated = crud.get_videos(sqlite_session)[0]
    assert updated.status == VideoStatus.SUCCESS
    assert updated.name == "name"
    assert updated.deleted_reason == "reason"
    assert updated.last_checked is not None


@pytest.mark.integration
def test_update_video_no_last_checked(sqlite_session: Session) -> None:
    video = crud.add_video_to_db(sqlite_session, "v1", datetime(2025, 1, 1))

    crud.update_video(
        sqlite_session,
        video=video,
        update_last_checked=False,
        status=VideoStatus.SUCCESS,
    )

    updated = crud.get_videos(sqlite_session)[0]
    assert updated.status == VideoStatus.SUCCESS
    assert updated.last_checked is None


@pytest.mark.integration
@pytest.mark.parametrize(
    ("from_val", "to_val", "result_val"),
    [
        (False, True, True),
        (False, False, False),
        (True, False, True),
        (True, True, True),
        (True, None, True),
    ],
)
def test_update_video_updates_source(
    sqlite_session: Session, from_val: bool, to_val: bool, result_val: bool
) -> None:
    video = crud.add_video_to_db(
        sqlite_session, "v1", datetime(2025, 1, 1), liked=from_val, saved=from_val
    )
    crud.update_video(sqlite_session, video=video, liked=to_val, saved=to_val)
    updated = crud.get_videos(sqlite_session)[0]
    assert updated.liked == result_val
    assert updated.saved == result_val
