import collections
import itertools
import logging
import re
from pathlib import Path

import yt_dlp
from gallery_dl import config, job
from yt_dlp.extractor.tiktok import TikTokIE, TikTokUserIE
from yt_dlp.utils import ExtractorError, traverse_obj

from atp.media import render_slideshow, temp_files_cleanup
from atp.models import VideoType
from atp.settings import (
    ANTI_BOT_BYPASS,
    COOKIES_FILE,
    DOWNLOADS_DIR,
    MAX_RETRIES,
    SLIDESHOW_TMP_DIR,
)

logger = logging.getLogger(__name__)

# Настройка gallery_dl
config.load()
config.set((), "directory", "")
config.set(("extractor",), "base-directory", str(SLIDESHOW_TMP_DIR))
config.set(
    ("extractor", "tiktok"),
    "filename",
    {"extension == 'mp3'": "audio.mp3", "": "{num}.{extension}"},
)


class YtDlpLogger:
    def __init__(self, quiet: bool = False, no_warnings: bool = False, **_):
        self.quiet = quiet
        self.no_warnings = no_warnings

    def debug(self, msg: str) -> None:
        if self.quiet:
            return
        if msg.startswith("[debug] "):
            logger.debug(msg)
        else:
            logger.info(msg)

    def warning(self, msg: str) -> None:
        if self.quiet or self.no_warnings:
            return
        logger.warning(msg)

    def error(self, msg: str) -> None:
        logger.error(msg)


VideoInfo = collections.namedtuple(
    "VideoInfo", ["name", "author", "type", "deleted_reason"], defaults=[None, None, None, None]
)


class NetworkError(Exception):
    """Исключение при сетевых ошибках."""

    pass


COOKIE_ERROR = "Log in for access"


class TikTokLikedIE(TikTokUserIE):
    IE_NAME = "tiktok:liked"
    _VALID_URL = (
        r"(?:tiktokliked:|https?://(?:www\.)?tiktok\.com/@)(?P<id>[\w.-]+)/liked/?(?:$|[#?])"
    )

    _API_BASE_URL = "https://www.tiktok.com/api/favorite/item_list"

    def _build_web_query(self, sec_uid, cursor):
        query = super()._build_web_query(sec_uid, cursor)
        query.pop("type", None)
        query["count"] = 35
        return query

    def _entries(self, sec_uid, user_name):
        display_id = user_name or sec_uid
        seen_ids = set()

        cursor = 0
        for page in itertools.count(1):
            for retry in self.RetryManager():
                response = self._download_json(
                    self._API_BASE_URL,
                    display_id,
                    f"Downloading page {page}",
                    query=self._build_web_query(sec_uid, cursor),
                )

                # Avoid infinite loop caused by bad device_id
                # See: https://github.com/yt-dlp/yt-dlp/issues/14031
                current_batch = sorted(traverse_obj(response, ("itemList", ..., "id", {str})))
                if not current_batch:
                    raise ExtractorError(
                        "This user's liked videos are not open to the public. "
                        "Open it or log into this account",
                        expected=True,
                    )
                if current_batch == sorted(seen_ids):
                    message = "TikTok API keeps sending the same page"
                    if self._KNOWN_DEVICE_ID:
                        raise ExtractorError(
                            f"{message}. Try again with a different device_id", expected=True
                        )
                    # The user didn't pass a device_id so we can reset it and retry
                    del self._DEVICE_ID
                    retry.error = ExtractorError(
                        f"{message}. Taking measures to avoid an infinite loop", expected=True
                    )

            for video in traverse_obj(response, ("itemList", lambda _, v: v["id"])):
                video_id = video["id"]
                if video_id in seen_ids:
                    continue
                seen_ids.add(video_id)
                webpage_url = self._create_url(user_id=None, video_id=video_id)
                yield self.url_result(
                    webpage_url,
                    TikTokIE,
                    **self._parse_aweme_video_web(video, webpage_url, video_id, extract_flat=True),
                )

            if not response.get("hasMore"):
                return

            old_cursor = cursor
            cursor = response.get("cursor")
            if not cursor or cursor == old_cursor:
                return

    def _real_extract(self, url):
        user_name, sec_uid = self._match_id(url), None
        if re.fullmatch(r"MS4wLjABAAAA[\w-]{64}", user_name):
            user_name, sec_uid = None, user_name
        else:
            webpage = (
                self._download_webpage(
                    self._UPLOADER_URL_FORMAT % user_name,
                    user_name,
                    "Downloading user webpage",
                    "Unable to download user webpage",
                    fatal=False,
                    impersonate=True,
                )
                or ""
            )
            detail = (
                traverse_obj(
                    self._get_universal_data(webpage, user_name), ("webapp.user-detail", {dict})
                )
                or {}
            )
            favorite_count = traverse_obj(detail, ("userInfo", "stats", "diggCount", {int}))
            if not favorite_count and detail.get("statusCode") == 10222:
                self.raise_login_required(
                    "This user's account is private. Log into an account that has access"
                )
            elif favorite_count == 0:
                raise ExtractorError(
                    "This user's liked videos are not open to the public. "
                    "Open it or log into this account",
                    expected=True,
                )

            sec_uid = traverse_obj(detail, ("userInfo", "user", "secUid", {str}))
            if not sec_uid:
                sec_uid = self._extract_sec_uid_from_embed(user_name)

            if not sec_uid:
                raise ExtractorError(
                    "Unable to extract secondary user ID. If you are able to get the channel_id "
                    'from a video posted by this user, try using "tiktokliked:channel_id/liked" '
                    "as the input URL (replacing `channel_id` with its actual value)",
                    expected=True,
                )

        return self.playlist_result(self._entries(sec_uid, user_name), sec_uid, user_name)


def get_error_message(e: Exception) -> str:
    if hasattr(e, "orig_msg"):
        return e.orig_msg
    exc_info = getattr(e, "exc_info", None)
    if exc_info and (error := exc_info[1]):
        if hasattr(error, "orig_msg"):
            return error.orig_msg
        return str(error)
    return str(e)


def yt_dlp_request(
    ydl_opts: dict[str, any],
    video_id: str | None = None,
    username: str | None = None,
    download: bool = False,
) -> dict[str, any] | list[dict[str, any]]:
    """Выполняет запрос к yt-dlp с обработкой сетевых ошибок.

    :param ydl_opts: Опции для yt-dlp
    :param video_id: ID видео
    :param username: Имя пользователя
    :param download: Флаг скачивания

    :return: Информация о видео или список видео

    :raises NetworkError: При сетевых ошибках
    :raises Exception: При других ошибках
    """
    if not (video_id or username):
        error_msg = "Either video_id or username must be provided"
        logger.error(error_msg)
        raise ValueError(error_msg)

    network_errors = [
        "Read timed out",
        "Failed to resolve",
        "Connection reset by peer",
        "Max retries exceeded",
        "Temporary failure in name resolution",
        "Connection aborted",
        "Unable to download webpage",
        "Unable to extract webpage video data",
        "Unsupported URL",
        "Failed to perform, curl",
    ]
    use_cookies = bool(username)
    if ANTI_BOT_BYPASS:
        ydl_opts["http_headers"] = {
            "User-Agent": "hi mom!"
        }  # передаём привет маме создателя анти-бот защиты (хз как, но пока это работает)
    ydl_opts["logger"] = YtDlpLogger(**ydl_opts)

    is_network_error = False
    last_exception = None
    attempt = 0
    while attempt < MAX_RETRIES:
        if COOKIES_FILE and use_cookies:
            # используем cookies только когда это необходимо
            ydl_opts["cookiefile"] = COOKIES_FILE
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if video_id:
                    return ydl.extract_info(f"https://www.tiktok.com/@/video/{video_id}/", download)
                elif username:
                    return TikTokLikedIE(ydl).extract(f"tiktokliked:{username}/liked")
        except Exception as e:
            last_exception = e
            error_msg = get_error_message(e)
            is_network_error = any(err in str(e) for err in network_errors)
            is_cookies_error = COOKIE_ERROR in error_msg

            if is_cookies_error and COOKIES_FILE and not use_cookies:
                # если ошибка из-за логина, добавляем cookies и пробуем снова не тратя attempt
                use_cookies = True
                continue

            logger.warning(
                f"Error requesting {'video' if video_id else 'user'} {video_id or username} "
                f"(attempt {attempt + 1}/{MAX_RETRIES}): {error_msg}"
            )

            attempt += 1

    # Если достигли максимального количества попыток или не сетевая ошибка
    if is_network_error:
        logger.error(
            "Network error detected, skipping\n"
            f"Try to {'disable' if ANTI_BOT_BYPASS else 'enable'} ANTI_BOT_BYPASS in settings.conf"
        )
        raise NetworkError
    else:
        raise last_exception


def check_video_availability(video_id: str) -> VideoInfo | None:
    """Проверяет доступность видео TikTok.

    :param video_id: ID видео

    :return: Информация о видео или None при сетевой ошибке
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        yt_dlp_request(ydl_opts, video_id=video_id)
        return VideoInfo(deleted_reason=None)
    except NetworkError:
        return None
    except Exception as e:
        error_msg = get_error_message(e)
        logger.error("Error checking video %s: %s", video_id, error_msg)
        return VideoInfo(deleted_reason=error_msg)


def get_user_liked_videos(username: str) -> list[dict]:
    """Получает список ID видео, которые пользователь отметил как понравившиеся.

    :param username: Имя пользователя

    :return: Список ID видео
    """
    ydl_opts = {
        "quiet": False,
        "no_warnings": False,
        "skip_download": True,
    }

    try:
        info = yt_dlp_request(ydl_opts, username=username)
        return info.get("entries", [])
    except Exception:
        return []


def download_video(video_id: str) -> VideoInfo | None:
    """Загружает видео TikTok.

    :param video_id: ID видео

    :return: Информация о видео или None при сетевой ошибке
    """
    ydl_opts = {
        "format": "best",
        "outtmpl": str(Path(DOWNLOADS_DIR) / f"{video_id}.mp4"),
        "quiet": False,
        "no_warnings": False,
    }

    error_msg = None
    try:
        info = yt_dlp_request(ydl_opts, video_id=video_id, download=True)
        if info["format_id"] == "audio":
            success = download_slideshow(video_id)
            if not success:
                return None
            video_type = VideoType.SLIDESHOW
        else:
            video_type = VideoType.VIDEO

        return VideoInfo(name=info["description"], author=info["uploader"], type=video_type)
    except NetworkError:
        return None
    except Exception as e:
        error_msg = get_error_message(e)
        logger.error("Error downloading video %s: %s", video_id, error_msg)
        return VideoInfo(deleted_reason=error_msg)


def download_slideshow(video_id: str) -> bool:
    logger.info("Processing slideshow: %s", video_id)

    temp_files_cleanup()

    # Загрузка изображений и аудио
    try:
        job.DownloadJob(f"https://www.tiktok.com/share/video/{video_id}").run()
    except Exception as e:
        logger.error("Error downloading images for the slideshow: %s", e)
        return False

    # Создание слайдшоу
    return render_slideshow(video_id)
