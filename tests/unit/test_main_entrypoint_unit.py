import logging

import pytest

from atp import __main__ as atp_main
from atp import app


@pytest.mark.unit
def test_setup_logging_falls_back_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")
    atp_main.setup_logging()
    assert logging.getLogger().level == logging.INFO


@pytest.mark.unit
def test_run_download_from_file_calls_import_and_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(app, "import_from_file", lambda: calls.append("import"))
    monkeypatch.setattr(app, "download_new_videos", lambda: calls.append("download"))
    app.run_download_from_file()
    assert calls == ["import", "download"]


@pytest.mark.unit
def test_run_download_from_tiktok_calls_import_and_download(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(app, "import_from_tiktok", lambda: calls.append("import"))
    monkeypatch.setattr(app, "download_new_videos", lambda: calls.append("download"))
    app.run_download_from_tiktok()
    assert calls == ["import", "download"]
