import io
from types import SimpleNamespace

import pytest

from atp import settings, telegram


@pytest.mark.integration
def test_send_media_single_video(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")

    def fake_post(url: str, data: dict, files: dict, timeout: int):  # noqa: ARG001
        assert url.endswith("/sendVideo")
        assert data["chat_id"] == "chat"
        assert "video" in files
        return SimpleNamespace(status_code=200, json=lambda: {"result": {"message_id": 1}})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    result = telegram.send_media(caption="c", video=io.BytesIO(b"v"))
    assert result["message_id"] == 1


@pytest.mark.integration
def test_send_media_group_uses_send_media_group_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "chat")

    def fake_post(url: str, data: dict, files: dict, timeout: int):  # noqa: ARG001
        assert url.endswith("/sendMediaGroup")
        assert data["chat_id"] == "chat"
        assert set(files) == {"photo0", "photo1"}
        return SimpleNamespace(status_code=200, json=lambda: {"result": [{"message_id": 10}]})

    monkeypatch.setattr(telegram.requests, "post", fake_post)
    result = telegram.send_media(caption="c", photos=[io.BytesIO(b"1"), io.BytesIO(b"2")])
    assert isinstance(result, list)
    assert result[0]["message_id"] == 10


@pytest.mark.integration
def test_discover_chat_id_sets_value_and_sends_probe_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    writes: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "set_config_value", lambda k, v: writes.append((k, v)))

    update_payload = {
        "result": [
            {
                "message": {
                    "chat": {
                        "id": -1415926589830,
                        "title": "test-channel",
                    }
                }
            }
        ]
    }

    def fake_get(_url: str, timeout: int):  # noqa: ARG001
        return SimpleNamespace(status_code=200, json=lambda: update_payload, text="ok")

    def fake_post(_url: str, data: dict, timeout: int):  # noqa: ARG001
        assert data["chat_id"] == str(-1415926589830)
        return SimpleNamespace(status_code=200, text="ok")

    monkeypatch.setattr(telegram.requests, "get", fake_get)
    monkeypatch.setattr(telegram.requests, "post", fake_post)

    telegram.discover_chat_id()

    assert str(-1415926589830) == settings.TELEGRAM_CHAT_ID
    assert ("TELEGRAM_CHAT_ID", str(-1415926589830)) in writes
