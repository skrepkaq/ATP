from types import SimpleNamespace

import pytest

from atp import tiktok
from atp.models import Video, VideoStatus, VideoType


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
@pytest.mark.parametrize("i", range(len(tiktok.COOKIE_ERRORS)))
def test_yt_dlp_request_retries_with_cookies_on_login_error(
    monkeypatch: pytest.MonkeyPatch,
    i: int,
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
                raise Exception(tiktok.COOKIE_ERRORS[i])
            return {"ok": True}

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 1)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", "/tmp/cookies.txt")

    result = tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/123")

    assert result == {"ok": True}
    assert "cookiefile" not in calls[0]
    assert calls[1]["cookiefile"] == "/tmp/cookies.txt"


@pytest.mark.unit
@pytest.mark.parametrize("always_retry", [False, True])
def test_yt_dlp_request_raises_network_error_after_retries(
    monkeypatch: pytest.MonkeyPatch,
    always_retry: bool,
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
            raise Exception("Read timed out")

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 3)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", None)

    with pytest.raises(tiktok.NetworkError):
        tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/123", always_retry=always_retry)

    assert len(calls) == 3


@pytest.mark.unit
@pytest.mark.parametrize(
    ("always_retry", "expected_calls"),
    [
        (False, 1),
        (True, 3),
    ],
)
def test_yt_dlp_request_raises_non_network_error(
    monkeypatch: pytest.MonkeyPatch,
    always_retry: bool,
    expected_calls: int,
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
            raise ValueError("bad data")

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 3)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", None)

    with pytest.raises(ValueError, match="bad data"):
        tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/123", always_retry=always_retry)

    assert len(calls) == expected_calls


@pytest.mark.unit
def test_yt_dlp_request_raises_correct_error_after_different_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class FakeYDLBase:
        def __init__(self, opts: dict):
            calls.append(dict(opts))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            pass

    class FakeYDLBadNetwork(FakeYDLBase):
        def extract_info(self, *_args, **_kwargs):
            if len(calls) == 1:
                raise ValueError("bad data")
            else:
                raise ValueError("Read timed out")

    class FakeYDLNetworkBad(FakeYDLBase):
        def extract_info(self, *_args, **_kwargs):
            if len(calls) == 1:
                raise ValueError("Read timed out")
            else:
                raise ValueError("bad data")

    monkeypatch.setattr(tiktok, "MAX_RETRIES", 3)
    monkeypatch.setattr(tiktok, "COOKIES_FILE", None)

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDLBadNetwork)
    with pytest.raises(tiktok.NetworkError):
        tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/123", always_retry=True)
    assert len(calls) == 3

    calls = []
    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDLNetworkBad)
    with pytest.raises(ValueError, match="bad data"):
        tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/123", always_retry=False)
    assert len(calls) == 2

    calls = []
    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDLNetworkBad)
    with pytest.raises(ValueError, match="bad data"):
        tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/123", always_retry=True)
    assert len(calls) == 3


@pytest.mark.unit
def test_yt_dlp_request_sets_user_agent_header(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeYDL:
        def __init__(self, opts: dict):
            assert opts["http_headers"]["User-Agent"] == "user-agent"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            return {"ok": True}

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "USER_AGENT", "user-agent")
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 1)

    assert tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/1") == {"ok": True}


@pytest.mark.unit
@pytest.mark.parametrize("always_retry", [False, True])
def test_yt_dlp_request_success_after_network_error(
    monkeypatch: pytest.MonkeyPatch, always_retry: bool
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
                raise ValueError("Read timed out")
            else:
                return {"ok": True}

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(tiktok, "MAX_RETRIES", 3)

    assert tiktok.yt_dlp_request(
        {}, "https://www.tiktok.com/@/video/1", always_retry=always_retry
    ) == {"ok": True}
    assert len(calls) == 2


@pytest.mark.unit
def test_yt_dlp_request_success_after_different_errors_with_always_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class FakeYDLBase:
        def __init__(self, opts: dict):
            calls.append(dict(opts))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, *_args, **_kwargs):
            pass

    class FakeYDLBadNetworkOk(FakeYDLBase):
        def extract_info(self, *_args, **_kwargs):
            if len(calls) == 1:
                raise ValueError("bad data")
            elif len(calls) == 2:
                raise ValueError("Read timed out")
            else:
                return {"ok": True}

    class FakeYDLNetworkBadOk(FakeYDLBase):
        def extract_info(self, *_args, **_kwargs):
            if len(calls) == 1:
                raise ValueError("Read timed out")
            elif len(calls) == 2:
                raise ValueError("bad data")
            else:
                return {"ok": True}

    monkeypatch.setattr(tiktok, "MAX_RETRIES", 3)

    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDLBadNetworkOk)
    assert tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/1", always_retry=True) == {
        "ok": True
    }
    assert len(calls) == 3

    calls = []
    monkeypatch.setattr(tiktok.yt_dlp, "YoutubeDL", FakeYDLNetworkBadOk)
    assert tiktok.yt_dlp_request({}, "https://www.tiktok.com/@/video/1", always_retry=True) == {
        "ok": True
    }
    assert len(calls) == 3


@pytest.mark.unit
def test_download_video_returns_none_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(tiktok.NetworkError()),  # noqa: ARG005
    )
    assert tiktok.download_video(Video(id="1", status=VideoStatus.NEW)) is None


@pytest.mark.unit
def test_download_video_sets_deleted_reason_on_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("boom")),  # noqa: ARG005
    )
    result = tiktok.download_video(Video(id="1", status=VideoStatus.NEW))
    assert result is not None
    assert result.deleted_reason == "boom"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "expected_always_retry"),
    [
        (VideoStatus.NEW, True),
        (VideoStatus.FAILED, False),
    ],
)
def test_download_video_calls_always_retry(
    monkeypatch: pytest.MonkeyPatch,
    status: VideoStatus,
    expected_always_retry: bool,
) -> None:
    always_retry = None

    def yt_dlp_request(*_args, **kwargs):
        nonlocal always_retry
        always_retry = kwargs["always_retry"]
        return {  # noqa: ARG005
            "format_id": "h264",
            "description": "desc",
            "uploader": "author",
        }

    monkeypatch.setattr(tiktok, "yt_dlp_request", yt_dlp_request)
    tiktok.download_video(Video(id="1", status=status))
    assert always_retry is expected_always_retry


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

    result = tiktok.download_video(Video(id="1", status=VideoStatus.NEW))

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

    assert tiktok.download_video(Video(id="1", status=VideoStatus.NEW)) is None


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

    result = tiktok.download_video(Video(id="1", status=VideoStatus.NEW))

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
    assert tiktok.check_video_availability(Video(id="1", status=VideoStatus.SUCCESS)) is None


@pytest.mark.unit
def test_check_video_availability_returns_reason_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("gone(r)")),  # noqa: ARG005
    )
    result = tiktok.check_video_availability(Video(id="1", status=VideoStatus.SUCCESS))
    assert result is not None
    assert result.deleted_reason == "gone(r)"


@pytest.mark.unit
def test_check_video_availability_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tiktok, "yt_dlp_request", lambda *args, **kwargs: {"ok": 1})  # noqa: ARG005
    result = tiktok.check_video_availability(Video(id="1", status=VideoStatus.SUCCESS))
    assert result is not None
    assert result.deleted_reason is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "expected_always_retry"),
    [
        (VideoStatus.SUCCESS, True),
        (VideoStatus.DELETED, False),
    ],
)
def test_check_video_availability_calls_always_retry(
    monkeypatch: pytest.MonkeyPatch, status: VideoStatus, expected_always_retry: bool
) -> None:
    always_retry = None

    def yt_dlp_request(*_args, **kwargs):
        nonlocal always_retry
        always_retry = kwargs["always_retry"]
        return {  # noqa: ARG005
            "format_id": "h264",
            "description": "desc",
            "uploader": "author",
        }

    monkeypatch.setattr(tiktok, "yt_dlp_request", yt_dlp_request)
    tiktok.check_video_availability(Video(id="1", status=status))
    assert always_retry is expected_always_retry


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
def test_get_user_saved_videos_returns_empty_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("x")),  # noqa: ARG005
    )
    assert tiktok.get_user_saved_videos("u") == []


@pytest.mark.unit
def test_get_user_saved_videos_returns_empty_on_no_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: {"entries": [{"id": "1"}]},  # noqa: ARG005
    )
    assert tiktok.get_user_saved_videos() == []


@pytest.mark.unit
def test_get_user_saved_videos_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tiktok,
        "yt_dlp_request",
        lambda *args, **kwargs: {"entries": [{"id": "1"}]},  # noqa: ARG005
    )
    monkeypatch.setattr(tiktok, "COOKIES_FILE", "/tmp/cookies.txt")
    assert tiktok.get_user_saved_videos() == [{"id": "1"}]


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
