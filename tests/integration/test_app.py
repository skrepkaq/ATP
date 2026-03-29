from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from atp import app, crud, video_import


class _FakeJob:
    def __init__(self, scheduled: list):
        self.scheduled = scheduled
        self.ts = None

    def at(self, ts: str):
        self.ts = ts
        return self

    def do(self, fn):
        self.scheduled.append((self.ts, fn.__name__))
        return self

    @property
    def hour(self):
        return self


@pytest.mark.integration
def test_run_scheduler_registers_jobs_and_bootstraps(
    sqlite_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "run_download_from_file", lambda: None)
    monkeypatch.setattr(app, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(crud, "get_videos", lambda _db: [object()])
    monkeypatch.setattr(app, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(app, "discover_chat_id", lambda: called.append("discover"))
    monkeypatch.setattr(app, "TIKTOK_USER", "u")
    monkeypatch.setattr(app.schedule, "every", lambda: _FakeJob(scheduled))
    monkeypatch.setattr(
        app.schedule,
        "run_pending",
        lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(app.time, "sleep", lambda _s: None)

    with pytest.raises(KeyboardInterrupt):
        app.run_scheduler()

    assert called == ["migrations", "discover"]
    assert ("00:00", "check_video_batch") in scheduled
    assert ("30:00", "run_download_from_tiktok") in scheduled


@pytest.mark.integration
def test_main_download_from_file_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        app.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(download_from_file=True),
    )
    monkeypatch.setattr(video_import, "deprecated_run", lambda: called.append("deprecated_run"))
    monkeypatch.setattr(app, "run_scheduler", lambda: called.append("scheduler"))

    app.main()

    assert called == ["deprecated_run"]


@pytest.mark.integration
def test_run_scheduler_without_tiktok_user_warns_and_skips_tiktok_job(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[str] = []
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(app, "discover_chat_id", lambda: called.append("discover"))
    monkeypatch.setattr(app, "run_download_from_file", lambda: called.append("download_from_file"))
    monkeypatch.setattr(app, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(crud, "get_videos", lambda _db: [object()])
    monkeypatch.setattr(app, "TIKTOK_USER", "")
    monkeypatch.setattr(app.schedule, "every", lambda: _FakeJob(scheduled))
    monkeypatch.setattr(
        app.schedule,
        "run_pending",
        lambda: (_ for _ in ()).throw(KeyboardInterrupt()),
    )
    monkeypatch.setattr(app.time, "sleep", lambda _s: None)

    with pytest.raises(KeyboardInterrupt):
        app.run_scheduler()

    assert called == ["migrations", "discover", "download_from_file"]
    assert ("00:00", "check_video_batch") in scheduled
    assert not any(job_name == "run_download_from_tiktok" for _ts, job_name in scheduled)


@pytest.mark.integration
def test_run_scheduler_exits_when_no_videos_after_bootstrap(
    sqlite_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(app, "run_migrations", lambda: None)
    monkeypatch.setattr(app, "discover_chat_id", lambda: None)
    monkeypatch.setattr(app, "run_download_from_file", lambda: None)
    monkeypatch.setattr(app, "get_db_session", lambda: sqlite_session)
    monkeypatch.setattr(crud, "get_videos", lambda _db: [])

    with pytest.raises(SystemExit) as exc_info:
        app.run_scheduler()

    assert exc_info.value.code == 1


@pytest.mark.integration
def test_main_default_runs_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        app.argparse.ArgumentParser,
        "parse_args",
        lambda _self: SimpleNamespace(download_from_file=False),
    )
    monkeypatch.setattr(app, "run_scheduler", lambda: called.append("scheduler"))
    app.main()
    assert called == ["scheduler"]
