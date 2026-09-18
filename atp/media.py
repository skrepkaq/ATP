import io
import logging
import os
import random
import shutil
from pathlib import Path

import ffmpeg

from atp import settings
from atp.settings import DOWNLOADS_DIR, PARTS_TMP_DIR, SLIDESHOW_TMP_DIR

logger = logging.getLogger(__name__)


def _ffmpeg_stderr_message(error: ffmpeg.Error) -> str:
    if isinstance(error.stderr, bytes):
        return error.stderr.decode("utf-8", errors="replace")
    return str(error)


def _probe_duration(media_path: Path) -> float | None:
    try:
        probe = ffmpeg.probe(str(media_path))
    except ffmpeg.Error as e:
        logger.error("Error probing media, try again: %s", _ffmpeg_stderr_message(e))
        return None

    duration = probe.get("format", {}).get("duration")
    if duration is None:
        return None

    try:
        return float(duration)
    except (TypeError, ValueError):
        return None


def _slide_duration(
    index: int, image_count: int, slide_duration: float, hold_last_frame: float
) -> float:
    if index == image_count - 1:
        return slide_duration + hold_last_frame
    return slide_duration


_SLIDE_VF = (
    "scale=1080:1920:force_original_aspect_ratio=decrease,"
    "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
    "format=yuv420p,"
    "setsar=1"
)


def _concat_file_line(path: Path) -> str:
    escaped = str(path).replace("'", r"'\''")
    return f"file '{escaped}'"


def _write_concat_list(entries: list[tuple[Path, float]], list_path: Path) -> None:
    lines = ["ffconcat version 1.0"]
    for path, duration in entries:
        lines.append(_concat_file_line(path))
        lines.append(f"duration {duration}")
    # duration последнего файла применяется только до следующего file
    lines.append(_concat_file_line(entries[-1][0]))
    list_path.write_text("\n".join(lines) + "\n")


def render_slideshow(video_id: str) -> bool:
    """Рендерит слайдшоу из изображений и аудио"""
    image_files: list[str] = [f for f in os.listdir(SLIDESHOW_TMP_DIR) if f.endswith(".jpg")]
    image_files.sort(key=lambda f: int(os.path.splitext(f)[0]))
    image_count = len(image_files)

    if not image_files:
        logger.error("No images were found")
        return False

    audio_path = Path(SLIDESHOW_TMP_DIR) / "audio.mp3"
    sound_len = _probe_duration(audio_path)
    if sound_len is None:
        # Звук скорее всего недоступен, попробуйте скачать видео заново
        # Если ошибка остаётся, создайте issue
        logger.error("Error downloading audio, try again")
        return False

    # Рассчитываем интервал в диапазоне [2, 3] сек
    t = max(2, min(3, sound_len / image_count))
    slideshow_len = t * image_count
    total_video_len = max(slideshow_len, sound_len)
    hold_last_frame = total_video_len - slideshow_len

    logger.info("Rendering slideshow: %d images, %d seconds total", image_count, total_video_len)

    output_path = Path(SLIDESHOW_TMP_DIR) / "output.mp4"
    concat_list_path = Path(SLIDESHOW_TMP_DIR) / "concat.txt"
    entries = [
        (
            SLIDESHOW_TMP_DIR / name,
            _slide_duration(index, image_count, t, hold_last_frame),
        )
        for index, name in enumerate(image_files)
    ]
    try:
        if image_count == 1:
            # Concat demuxer of one JPEG emits a single frame (6s/60s class of bug)
            video = ffmpeg.input(str(entries[0][0]), loop=1, t=total_video_len, framerate=30)
        else:
            _write_concat_list(entries, concat_list_path)
            video = ffmpeg.input(str(concat_list_path), format="concat", safe=0)
        (
            ffmpeg.output(
                video,
                ffmpeg.input(str(audio_path)),
                str(output_path),
                vf=_SLIDE_VF,
                r=30,
                fps_mode="cfr",
                g=900,
                acodec="aac",
                vcodec="libx264",
                tune="stillimage",
                t=total_video_len,
                movflags="+faststart",
                loglevel="error",
            )
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        logger.error("Error rendering slideshow: %s", _ffmpeg_stderr_message(e))
        return False

    if output_path.exists():
        # Копирование результата в директорию загрузок
        target_path = Path(DOWNLOADS_DIR) / f"{video_id}.mp4"
        shutil.copy(output_path, target_path)
        logger.info("Slideshow saved: %s.mp4", video_id)
        return True
    return False


def generate_bmp(seed: int | str) -> io.BytesIO:
    """Генерирует BMP картинку случайного цвета."""
    random.seed(seed)

    color = [0, random.randint(0, 255), 255]
    random.shuffle(color)

    base_bmp_hex = "424d1e000000000000001a0000000c0000000100010001001800"
    bmp_data = bytes.fromhex(base_bmp_hex) + bytes(color) + b"\x00"
    return io.BytesIO(bmp_data)


def split_video(video_path: Path, parts: int) -> list[Path]:
    total_duration = _probe_duration(video_path)
    if total_duration is None:
        return []

    part_duration = total_duration / parts

    output_paths = []
    for i in range(parts):
        logger.info("Rendering %s/%s part", i + 1, parts)
        start_time = i * part_duration
        output_path = PARTS_TMP_DIR / f"{video_path.stem}_part{i + 1}.mp4"
        bitrate_coef = 0.95
        while bitrate_coef > 0.5:
            max_bits = int(settings.TELEGRAM_MAX_VIDEO_SIZE * bitrate_coef) * 8
            total_bitrate = int(max_bits / part_duration)

            audio_bitrate = 64_000
            video_bitrate_k = max(total_bitrate - audio_bitrate, 200_000) // 1000

            try:
                (
                    ffmpeg.input(str(video_path), ss=f"{start_time:.3f}", t=f"{part_duration:.3f}")
                    .output(
                        str(output_path),
                        vcodec="libx265",
                        acodec="copy",
                        movflags="+faststart",
                        **{
                            "b:v": f"{video_bitrate_k}k",
                            "maxrate": f"{video_bitrate_k}k",
                            "bufsize": f"{video_bitrate_k * 2}k",
                        },
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            except ffmpeg.Error:
                temp_files_cleanup()
                return []
            video_len = get_file_size(output_path)
            if video_len > settings.TELEGRAM_MAX_VIDEO_SIZE:
                bitrate_coef -= 0.05
                logger.warning(
                    "Video is too large: %s bytes. Trying again with lower bitrate.", video_len
                )
                continue
            output_paths.append(output_path)
            break

    return output_paths


def get_file_size(file_path: Path) -> int:
    with open(file_path, "rb") as file:
        return file.seek(0, io.SEEK_END)


def temp_files_cleanup() -> None:
    for dir in [SLIDESHOW_TMP_DIR, PARTS_TMP_DIR]:
        for file in dir.iterdir():
            try:
                os.remove(file)
            except Exception as e:
                logger.warning("Error deleting %s: %s", file, e)
