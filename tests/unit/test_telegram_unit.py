import io
from types import SimpleNamespace

import pytest

from atp import settings, telegram


@pytest.mark.unit
def test_send_media_raises_when_telegram_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    with pytest.raises(Exception, match="not configured"):
        telegram.send_media(caption="x", video=io.BytesIO(b"v"))


@pytest.mark.unit
def test_send_media_requires_video_or_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")
    with pytest.raises(ValueError, match="Either video or photos"):
        telegram.send_media(caption="x")


@pytest.mark.unit
def test_send_media_raises_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(
        telegram.requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(status_code=400, text="bad"),  # noqa: ARG005
    )
    with pytest.raises(Exception, match="Failed to send Telegram media"):
        telegram.send_media(caption="x", video=io.BytesIO(b"v"))


@pytest.mark.unit
def test_edit_media_returns_false_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    assert telegram.edit_media(1, "c", video=io.BytesIO(b"x")) is False


@pytest.mark.unit
def test_edit_media_returns_false_without_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")
    assert telegram.edit_media(1, "c") is False


@pytest.mark.unit
def test_edit_media_returns_false_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")
    monkeypatch.setattr(
        telegram.requests,
        "post",
        lambda *args, **kwargs: SimpleNamespace(status_code=400, text="bad"),  # noqa: ARG005
    )
    assert telegram.edit_media(1, "c", video=io.BytesIO(b"x")) is False


@pytest.mark.unit
def test_edit_media_success_with_parse_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")
    captured = {}

    def fake_post(url: str, data: dict, files: dict, timeout: int):  # noqa: ARG001
        captured["data"] = data
        captured["files"] = files
        return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    ok = telegram.edit_media(
        5,
        "caption",
        photo=io.BytesIO(b"x"),
        parse_mode="Markdown",
    )
    assert ok is True
    assert "photo" in captured["files"]
    assert "Markdown" in captured["data"]["media"]


@pytest.mark.unit
def test_discover_chat_id_returns_early_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    called = {"get": False}

    def _get(*args, **kwargs):  # noqa: ARG001
        called["get"] = True
        return None

    monkeypatch.setattr(telegram.requests, "get", _get)
    telegram.discover_chat_id()
    assert called["get"] is False


@pytest.mark.unit
def test_discover_chat_id_clears_chat_id_when_probe_message_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "set_config_value", lambda k, v: writes.append((k, v)))

    def fake_get(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(
            status_code=200,
            json=lambda: {
                "result": [{"message": {"chat": {"id": 123, "title": "x"}}}],
            },
            text="ok",
        )

    def fake_post(*args, **kwargs):  # noqa: ARG001
        return SimpleNamespace(status_code=400, text="forbidden")

    monkeypatch.setattr(telegram.requests, "get", fake_get)
    monkeypatch.setattr(telegram.requests, "post", fake_post)

    telegram.discover_chat_id()

    assert settings.TELEGRAM_CHAT_ID is None
    assert ("TELEGRAM_CHAT_ID", "") in writes


@pytest.mark.unit
def test_discover_chat_id_handles_failed_updates_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(settings, "set_config_value", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        telegram.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(status_code=500, text="err"),  # noqa: ARG005
    )
    telegram.discover_chat_id()
    assert settings.TELEGRAM_CHAT_ID == ""


@pytest.mark.unit
def test_discover_chat_id_handles_empty_updates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(settings, "set_config_value", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        telegram.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(  # noqa: ARG005
            status_code=200, text="ok", json=lambda: {"result": []}
        ),
    )
    telegram.discover_chat_id()
    assert settings.TELEGRAM_CHAT_ID == ""


@pytest.mark.unit
def test_discover_chat_id_clears_value_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "set_config_value", lambda k, v: writes.append((k, v)))
    monkeypatch.setattr(
        telegram.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),  # noqa: ARG005
    )
    telegram.discover_chat_id()
    assert settings.TELEGRAM_CHAT_ID is None
    assert ("TELEGRAM_CHAT_ID", "") in writes
