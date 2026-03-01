from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from atp import crud
from atp.models import VideoStatus


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
    crud.add_video_to_db(sqlite_session, "existing", datetime(2025, 1, 1))
    crud.add_videos_bulk(
        sqlite_session,
        [
            {"id": "existing", "date": datetime(2025, 1, 1)},
            {"id": "new", "date": datetime(2025, 1, 2)},
        ],
    )

    ids = {v.id for v in crud.get_videos(sqlite_session)}
    assert ids == {"existing", "new"}


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
