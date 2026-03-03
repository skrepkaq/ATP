from types import SimpleNamespace

import pytest

from atp import app


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
def test_run_scheduler_registers_jobs_and_bootstraps(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(app, "discover_chat_id", lambda: called.append("discover"))
    monkeypatch.setattr(app, "DOWNLOAD_FROM_TIKTOK", True)
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
    monkeypatch.setattr(app, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(app, "run_download_from_file", lambda: called.append("from_file"))
    monkeypatch.setattr(app, "run_scheduler", lambda: called.append("scheduler"))

    app.main()

    assert called == ["migrations", "from_file"]


@pytest.mark.integration
def test_run_scheduler_without_tiktok_import_job(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(app, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(app, "discover_chat_id", lambda: called.append("discover"))
    monkeypatch.setattr(app, "DOWNLOAD_FROM_TIKTOK", False)
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
    assert not any(job_name == "run_download_from_tiktok" for _ts, job_name in scheduled)


@pytest.mark.integration
def test_run_scheduler_without_tiktok_user_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(app, "run_migrations", lambda: called.append("migrations"))
    monkeypatch.setattr(app, "discover_chat_id", lambda: called.append("discover"))
    monkeypatch.setattr(app, "DOWNLOAD_FROM_TIKTOK", True)
    monkeypatch.setattr(app, "TIKTOK_USER", "")

    with pytest.raises(SystemExit) as exc_info:
        app.run_scheduler()

    assert exc_info.value.code == 1
    assert called == ["migrations", "discover"]


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
