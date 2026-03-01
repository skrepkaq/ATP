from types import SimpleNamespace

import pytest

from atp import tiktok
from atp.models import VideoType


@pytest.mark.unit
def test_get_error_message_prefers_orig_msg() -> None:
    exc = SimpleNamespace(orig_msg="original")
    assert tiktok.get_error_message(exc) == "original"


@pytest.mark.unit
def test_get_error_message_reads_nested_exc_info() -> None:
    nested = SimpleNamespace(orig_msg="nested")
    exc = SimpleNamespace(exc_info=(None, nested, None))
    assert tiktok.get_error_message(exc) == "nested"


@pytest.mark.unit
def test_yt_dlp_request_retries_with_cookies_on_login_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class FakeYDL:
        def __init__(self, opts: dict):
            calls.append(dict(opts))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            if len(calls) == 1:
                raise Exception(tiktok.COOKIE_ERROR)
            return {"ok": True}

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 2)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", "/tmp/cookies.txt")
    monkeypatch.setattr(tiktok, "ANTI_BOT_BYPASS", False)

    result = tiktok.yt_dlp_request({}, video_id="123")

    assert result == {"ok": True}
    assert "cookiefile" not in calls[0]
    assert calls[1]["cookiefile"] == "/tmp/cookies.txt"


@pytest.mark.unit
def test_yt_dlp_request_raises_network_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeYDL:
        def __init__(self, _opts: dict):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            raise Exception("Read timed out")

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 2)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", None)
    monkeypatch.setattr(tiktok, "ANTI_BOT_BYPASS", False)

    with pytest.raises(tiktok.NetworkError):
        tiktok.yt_dlp_request({}, video_id="123")


@pytest.mark.unit
def test_yt_dlp_request_raises_last_exception_for_non_network_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeYDL:
        def __init__(self, _opts: dict):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            raise ValueError("bad data")

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 1)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", None)
    monkeypatch.setattr(tiktok, "ANTI_BOT_BYPASS", False)

    with pytest.raises(ValueError, match="bad data"):
        tiktok.yt_dlp_request({}, video_id="123")


@pytest.mark.unit
def test_yt_dlp_request_sets_antibot_header(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYDL:
        def __init__(self, opts: dict):
            assert opts["http_headers"]["User-Agent"] == "hi mom!"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            return {"ok": True}

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "ANTI_BOT_BYPASS", True)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 1)

    assert tiktok.yt_dlp_request({}, video_id="1") == {"ok": True}


@pytest.mark.unit
def test_download_video_returns_none_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(tiktok.NetworkError()),  # noqa: ARG005
    )
    assert tiktok.download_video("1") is None


@pytest.mark.unit
def test_download_video_sets_deleted_reason_on_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),  # noqa: ARG005
    )
    result = tiktok.download_video("1")
    assert result is not None
    assert result.deleted_reason == "boom"


@pytest.mark.unit
def test_download_video_handles_slideshow_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: {  # noqa: ARG005
            "format_id": "audio",
            "description": "desc",
            "uploader": "author",
        },
    )
    monkeypatch.setattr(tiktok, "download_slideshow", lambda _id: True)

    result = tiktok.download_video("1")

    assert result is not None
    assert result.type == VideoType.SLIDESHOW
    assert result.deleted_reason is None


@pytest.mark.unit
def test_download_video_handles_slideshow_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: {  # noqa: ARG005
            "format_id": "audio",
            "description": "desc",
            "uploader": "author",
        },
    )
    monkeypatch.setattr(tiktok, "download_slideshow", lambda _id: False)

    assert tiktok.download_video("1") is None


@pytest.mark.unit
def test_download_video_regular_video_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: {  # noqa: ARG005
            "format_id": "h264",
            "description": "desc",
            "uploader": "author",
        },
    )

    result = tiktok.download_video("1")

    assert result is not None
    assert result.type == VideoType.VIDEO
    assert result.deleted_reason is None


@pytest.mark.unit
def test_check_video_availability_none_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(tiktok.NetworkError()),  # noqa: ARG005
    )
    assert tiktok.check_video_availability("1") is None


@pytest.mark.unit
def test_check_video_availability_returns_reason_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("gone(r)")),  # noqa: ARG005
    )
    result = tiktok.check_video_availability("1")
    assert result is not None
    assert result.deleted_reason == "gone(r)"


@pytest.mark.unit
def test_check_video_availability_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tiktok, "yt_dlp_request", lambda *args, **kwargs: {"ok": 1})  # noqa: ARG005
    result = tiktok.check_video_availability("1")
    assert result is not None
    assert result.deleted_reason is None


@pytest.mark.unit
def test_get_user_liked_videos_returns_empty_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("x")),  # noqa: ARG005
    )
    assert tiktok.get_user_liked_videos("u") == []


@pytest.mark.unit
def test_get_user_liked_videos_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: {"entries": [{"id": "1"}]},  # noqa: ARG005
    )
    assert tiktok.get_user_liked_videos("u") == [{"id": "1"}]


@pytest.mark.unit
def test_download_slideshow_returns_false_on_job_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tiktok, "temp_files_cleanup", lambda: None)

    class FakeJob:
        def __init__(self, _url: str):
            pass

        def run(self):
            raise RuntimeError("fail")

    monkeypatch.setattr(tiktok.job, "DownloadJob", FakeJob)
    assert tiktok.download_slideshow("1") is False


@pytest.mark.unit
def test_download_slideshow_returns_render_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tiktok, "temp_files_cleanup", lambda: None)

    class FakeJob:
        def __init__(self, _url: str):
            pass

        def run(self):
            return None

    monkeypatch.setattr(tiktok.job, "DownloadJob", FakeJob)
    monkeypatch.setattr(tiktok, "render_slideshow", lambda _id: True)
    assert tiktok.download_slideshow("1") is True
