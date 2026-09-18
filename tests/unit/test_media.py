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
        def __init__(self, path: str):
            self.path = path

        def overwrite_output(self):
            return self

        def run(self, **_kwargs):
            Path(self.path).write_bytes(b"mp4")

    outputs: list[tuple[str, dict]] = []

    class FakeStream:
        def filter(self, *_args, **_kwargs):
            return self

    def fake_output(*args, **kwargs):
        out_path = args[-1]
        outputs.append((str(out_path), kwargs))
        return FakeOutput(out_path)

    monkeypatch.setattr(media.ffmpeg, "input", lambda *_args, **_kwargs: FakeStream())
    monkeypatch.setattr(media.ffmpeg, "output", fake_output)

    assert media.render_slideshow("vid") is True
    concat = (slide_dir / "concat.txt").read_text()
    assert concat.startswith("ffconcat version 1.0")
    assert concat.count("file ") == 3
    assert "duration 3" in concat
    assert "duration 7" in concat
    assert len(outputs) == 1
    assert outputs[0][1]["vcodec"] == "libx264"
    assert outputs[0][1]["acodec"] == "aac"
    assert outputs[0][1]["fps_mode"] == "cfr"
    assert outputs[0][1]["r"] == 30
    assert outputs[0][1]["movflags"] == "+faststart"
    assert "scale=1080:1920" in outputs[0][1]["vf"]
    assert (out_dir / "vid.mp4").exists()


@pytest.mark.unit
def test_render_slideshow_returns_false_on_ffmpeg_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slide_dir = tmp_path / "slides"
    out_dir = tmp_path / "out"
    slide_dir.mkdir()
    out_dir.mkdir()
    (slide_dir / "1.jpg").write_bytes(b"jpg")
    (slide_dir / "audio.mp3").write_bytes(b"mp3")

    monkeypatch.setattr(media, "SLIDESHOW_TMP_DIR", slide_dir)
    monkeypatch.setattr(media, "DOWNLOADS_DIR", str(out_dir))
    monkeypatch.setattr(media.os, "listdir", lambda _p: ["1.jpg"])
    monkeypatch.setattr(media, "_probe_duration", lambda _p: 10.0)

    class FakeStream:
        def filter(self, *_args, **_kwargs):
            return self

    class FakeOutput:
        def overwrite_output(self):
            return self

        def run(self, **_kwargs):
            raise ffmpeg.Error("ffmpeg", b"", b"boom")

    monkeypatch.setattr(media.ffmpeg, "input", lambda *_args, **_kwargs: FakeStream())
    monkeypatch.setattr(media.ffmpeg, "output", lambda *_args, **_kwargs: FakeOutput())

    assert media.render_slideshow("vid") is False
    assert not (out_dir / "vid.mp4").exists()


@pytest.mark.unit
def test_render_slideshow_single_image_loops_instead_of_concat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slide_dir = tmp_path / "slides"
    out_dir = tmp_path / "out"
    slide_dir.mkdir()
    out_dir.mkdir()
    (slide_dir / "1.jpg").write_bytes(b"jpg")
    (slide_dir / "audio.mp3").write_bytes(b"mp3")

    monkeypatch.setattr(media, "SLIDESHOW_TMP_DIR", slide_dir)
    monkeypatch.setattr(media, "DOWNLOADS_DIR", str(out_dir))
    monkeypatch.setattr(media.os, "listdir", lambda _p: ["1.jpg"])
    monkeypatch.setattr(media, "_probe_duration", lambda _p: 10.0)

    inputs: list[tuple[str, dict]] = []
    outputs: list[dict] = []

    class FakeStream:
        def filter(self, *_args, **_kwargs):
            return self

    class FakeOutput:
        def overwrite_output(self):
            return self

        def run(self, **_kwargs):
            (slide_dir / "output.mp4").write_bytes(b"mp4")

    def fake_input(path, **kwargs):
        inputs.append((str(path), kwargs))
        return FakeStream()

    def fake_output(*_args, **kwargs):
        outputs.append(kwargs)
        return FakeOutput()

    monkeypatch.setattr(media.ffmpeg, "input", fake_input)
    monkeypatch.setattr(media.ffmpeg, "output", fake_output)

    assert media.render_slideshow("one") is True
    assert not (slide_dir / "concat.txt").exists()
    image_in = next(kwargs for path, kwargs in inputs if path.endswith("1.jpg"))
    assert image_in["loop"] == 1
    assert image_in["t"] == 10.0
    assert image_in["framerate"] == 30
    assert outputs[0]["movflags"] == "+faststart"


@pytest.mark.unit
def test_concat_file_line_escapes_single_quotes() -> None:
    line = media._concat_file_line(Path("/tmp/it's.mp4"))
    assert line == "file '/tmp/it'\\''s.mp4'"


@pytest.mark.unit
def test_write_concat_list_repeats_last_file(tmp_path: Path) -> None:
    a = tmp_path / "1.jpg"
    b = tmp_path / "2.jpg"
    list_path = tmp_path / "concat.txt"
    media._write_concat_list([(a, 3), (b, 7)], list_path)
    text = list_path.read_text()
    assert text.splitlines()[0] == "ffconcat version 1.0"
    assert text.count(f"file '{b}'") == 2
    assert "duration 3" in text
    assert "duration 7" in text


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
