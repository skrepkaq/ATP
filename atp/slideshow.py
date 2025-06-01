"""
Модуль для создания слайдшоу из изображений и аудио.

Модуль выполняет:
- Загрузку изображений и аудио из TikTok
- Рендер из них слайдшоу с помощью FFmpeg
- Сохранение готового видео
"""

import logging
import os
import shutil
import subprocess

from gallery_dl import config, job, output

from atp.settings import DOWNLOADS_DIR, TMP_DIR

# Настройка gallery_dl
config.load()
config.set((), "directory", "")
config.set(("extractor",), "base-directory", TMP_DIR)
config.set(
    ("extractor", "tiktok"),
    "filename",
    {"extension == 'mp3'": "audio.mp3", "": "{num}.{extension}"},
)

output.initialize_logging(logging.INFO)
output.configure_logging(logging.INFO)
output.setup_logging_handler("unsupportedfile", fmt="{message}")


def render_slideshow() -> bool:
    """Рендерит слайдшоу из изображений и аудио"""
    image_files: list[str] = [f for f in os.listdir(TMP_DIR) if f.endswith(".jpg")]
    image_files.sort()
    image_count = len(image_files)

    if not image_files:
        print("No images were found")
        return False

    audio_path = os.path.join(TMP_DIR, "audio.mp3")
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    sound_len = float(result.stdout)

    print(f"Number of JPG files in {TMP_DIR}: {image_count}")
    print(f"Sound length: {sound_len:.2f} seconds")

    # Рассчитываем интервал в диапазоне [2, 3] сек
    t = max(2, min(3, sound_len / image_count))
    print(f"Interval between images (X): {t:.2f} seconds")

    total_video_len = max(t * image_count, sound_len)
    print(f"Total video length: {total_video_len:.2f} seconds")

    # Частота кадров для входной последовательности изображений (1 кадр каждые X секунд)
    input_fps = 1 / t

    # Настройка фильтра для вертикального видео с правильным соотношением сторон
    vf = (
        "scale=iw*min(1080/iw\\,1920/ih):ih*min(1080/iw\\,1920/ih),"
        "pad=1080:1920:(1080-iw*min(1080/iw\\,1920/ih))/2:(1920-ih*min(1080/iw\\,1920/ih))/2,"
        "format=yuv420p"
    )

    command = [
        "ffmpeg",
        "-framerate",
        f"{input_fps}",
        "-i",
        f"{TMP_DIR}/%01d.jpg",
        "-i",
        audio_path,
        "-vf",
        vf,
        "-r",
        "30",  # Частота кадров выходного видео
        "-acodec",
        "aac",
        "-t",
        str(total_video_len),
        f"{TMP_DIR}/output.mp4",
        "-loglevel",
        "error",
        "-y",
    ]
    subprocess.run(command)

    return os.path.exists(os.path.join(TMP_DIR, "output.mp4"))


def download_slideshow(video_id: str) -> bool:
    print(f"Processing slideshow: {video_id}")

    # Очистка временной директории
    if os.path.exists(TMP_DIR):
        for file in os.listdir(TMP_DIR):
            try:
                os.remove(os.path.join(TMP_DIR, file))
            except Exception as e:
                print(f"Error deleting {file}: {e}")
    else:
        os.makedirs(TMP_DIR, exist_ok=True)

    # Загрузка изображений и аудио
    try:
        job.DownloadJob(f"https://www.tiktok.com/share/video/{video_id}").run()
    except Exception as e:
        print(f"Error downloading images for the slideshow: {e}")
        return False

    # Создание слайдшоу
    if not render_slideshow():
        return False

    # Копирование результата в директорию загрузок
    output_file_path = os.path.join(TMP_DIR, "output.mp4")
    if os.path.exists(output_file_path):
        os.makedirs(DOWNLOADS_DIR, exist_ok=True)
        target_path = os.path.join(DOWNLOADS_DIR, f"{video_id}.mp4")
        shutil.copy(output_file_path, target_path)
        print(f"Slideshow saved: {video_id}.mp4")
        return True

    return False
