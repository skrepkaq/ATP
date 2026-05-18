from pathlib import Path

import ffmpeg
import pytest

from atp import media


@pytest.mark.unit
def test_generate_bmp_is_deterministic() -> None:
    a = media.generate_bmp("seed").getvalue()
    b = media.generate_bmp("seed").getvalue()
    c = media.generate_bmp("other").getvalue()
    assert a == b
    assert a != c
    assert a[:2] == b"BM"


@pytest.mark.unit
def test_probe_duration_returns_none_on_ffmpeg_error(monkeypatch: pytest.MonkeyPatch) -> None:
    err = ffmpeg.Error("ffmpeg", b"", b"boom")
    monkeypatch.setattr(media.ffmpeg, "probe", lambda _path: (_ for _ in ()).throw(err))
    assert media._probe_duration(Path("/tmp/f.mp4")) is None


@pytest.mark.unit
def test_probe_duration_parses_float(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media.ffmpeg, "probe", lambda _path: {"format": {"duration": "12.5"}})
    assert media._probe_duration(Path("/tmp/f.mp4")) == 12.5


@pytest.mark.unit
def test_render_slideshow_returns_false_when_no_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(media, "SLIDESHOW_TMP_DIR", tmp_path)
    monkeypatch.setattr(media.os, "listdir", lambda _p: [])
    assert media.render_slideshow("1") is False


@pytest.mark.unit
def test_render_slideshow_returns_false_when_audio_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(media, "SLIDESHOW_TMP_DIR", tmp_path)
    monkeypatch.setattr(media.os, "listdir", lambda _p: ["1.jpg"])
    monkeypatch.setattr(media, "_probe_duration", lambda _p: None)
    assert media.render_slideshow("1") is False


@pytest.mark.unit
def test_render_slideshow_success_copies_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slide_dir = tmp_path / "slides"
    out_dir = tmp_path / "out"
    slide_dir.mkdir()
    out_dir.mkdir()
    (slide_dir / "1.jpg").write_bytes(b"jpg")
    (slide_dir / "2.jpg").write_bytes(b"jpg")
    (slide_dir / "audio.mp3").write_bytes(b"mp3")

    monkeypatch.setattr(media, "SLIDESHOW_TMP_DIR", slide_dir)
    monkeypatch.setattr(media, "DOWNLOADS_DIR", str(out_dir))
    monkeypatch.setattr(media.os, "listdir", lambda _p: ["1.jpg", "2.jpg"])
    monkeypatch.setattr(media, "_probe_duration", lambda _p: 10.0)

    class FakeOutput:
        def overwrite_output(self):
            return self

        def run(self, **_kwargs):
            (slide_dir / "output.mp4").write_bytes(b"mp4")

    slide_inputs: list[tuple[str, dict]] = []

    class FakeStream:
        def filter(self, *_args, **_kwargs):
            return self

    def fake_input(path, **kwargs):
        if str(path).endswith(".jpg"):
            slide_inputs.append((str(path), kwargs))
        return FakeStream()

    output_kwargs: dict = {}

    def fake_output(*_args, **kwargs):
        output_kwargs.update(kwargs)
        return FakeOutput()

    monkeypatch.setattr(media.ffmpeg, "input", fake_input)
    monkeypatch.setattr(media.ffmpeg, "concat", lambda *_streams, **_kwargs: FakeStream())
    monkeypatch.setattr(media.ffmpeg, "output", fake_output)

    assert media.render_slideshow("vid") is True
    assert len(slide_inputs) == 2
    assert slide_inputs[0][1]["loop"] == 1
    assert slide_inputs[0][1]["t"] == 3
    assert slide_inputs[1][1]["t"] == 7
    assert "vf" not in output_kwargs
    assert (out_dir / "vid.mp4").exists()


@pytest.mark.unit
def test_split_video_returns_empty_if_probe_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "_probe_duration", lambda _p: None)
    assert media.split_video(Path("/tmp/v.mp4"), 2) == []


@pytest.mark.unit
def test_split_video_returns_empty_on_ffmpeg_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "_probe_duration", lambda _p: 10.0)
    monkeypatch.setattr(media.settings, "TELEGRAM_MAX_VIDEO_SIZE", 1024 * 1024)
    called = {"cleanup": False}
    monkeypatch.setattr(media, "temp_files_cleanup", lambda: called.__setitem__("cleanup", True))

    class FakeInput:
        def output(self, *args, **kwargs):  # noqa: ARG002
            return self

        def overwrite_output(self):
            return self

        def run(self, **kwargs):  # noqa: ARG002
            raise ffmpeg.Error("ffmpeg", b"", b"bad")

    monkeypatch.setattr(media.ffmpeg, "input", lambda *args, **kwargs: FakeInput())  # noqa: ARG005

    assert media.split_video(Path("/tmp/v.mp4"), 2) == []
    assert called["cleanup"] is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "sizes",
    [
        [1500, 900, 900],  # part 1 retries once, part 2 fits first try
        [900, 1500, 900],  # part 1 fits first try, part 2 retries once
    ],
)
def test_split_video_retries_lower_bitrate_until_fits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sizes: list[int],
) -> None:
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x")
    monkeypatch.setattr(media, "_probe_duration", lambda _p: 10.0)
    monkeypatch.setattr(media.settings, "TELEGRAM_MAX_VIDEO_SIZE", 1000)
    monkeypatch.setattr(media, "PARTS_TMP_DIR", tmp_path)

    class FakeInput:
        def output(self, out_path: str, **kwargs):  # noqa: ARG002
            Path(out_path).write_bytes(b"x")
            return self

        def overwrite_output(self):
            return self

        def run(self, **kwargs):  # noqa: ARG002
            return None

    monkeypatch.setattr(media.ffmpeg, "input", lambda *args, **kwargs: FakeInput())  # noqa: ARG005
    size_iter = iter(sizes)
    monkeypatch.setattr(media, "get_file_size", lambda _path: next(size_iter))

    output_parts = media.split_video(video, 2)

    assert len(output_parts) == 2


@pytest.mark.unit
def test_temp_files_cleanup_ignores_remove_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "f1").write_text("x", encoding="utf-8")
    (b / "f2").write_text("x", encoding="utf-8")
    monkeypatch.setattr(media, "SLIDESHOW_TMP_DIR", a)
    monkeypatch.setattr(media, "PARTS_TMP_DIR", b)

    def fail_once(path):
        if str(path).endswith("f1"):
            raise OSError("x")
        Path(path).unlink()

    monkeypatch.setattr(media.os, "remove", fail_once)
    media.temp_files_cleanup()
    assert (a / "f1").exists()
    assert not (b / "f2").exists()
