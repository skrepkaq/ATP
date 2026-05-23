import itertools
import logging
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import yt_dlp
from gallery_dl import config, job
from yt_dlp.extractor.tiktok import TikTokIE, TikTokUserIE
from yt_dlp.utils import (
    ExtractorError,
    int_or_none,
)
from yt_dlp.utils.traversal import traverse_obj

from atp.media import render_slideshow, temp_files_cleanup
from atp.models import Video, VideoInfo, VideoStatus, VideoType
from atp.settings import (
    COOKIES_FILE,
    DOWNLOADS_DIR,
    MAX_RETRIES,
    SLIDESHOW_TMP_DIR,
    USER_AGENT,
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
    def __init__(
        self, quiet: bool = False, no_warnings: bool = False, no_errors: bool = False, **_
    ):
        self.quiet = quiet
        self.no_warnings = no_warnings
        self.no_errors = no_errors

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
        if self.no_errors:
            return
        logger.error(msg)


class NetworkError(Exception):
    """Исключение при сетевых ошибках."""

    pass


COOKIE_ERRORS = [
    "Log in for access",
    "status code 10203",
]
NETWORK_ERRORS = [
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
    "Unexpected response from webpage request",
]


class TikTokUserBaseIE(TikTokUserIE):
    _CURSOR_SCALE = 1000  # cursor is in milliseconds
    _FAIL_EARLY_MESSAGE = (
        "This user's account is likely either private or all of their videos are private. "
        "Log into an account that has access"
    )

    def _extract_universal_data(self, url, display_id=None, fatal=True):
        def get_webpage(note):
            res = self._download_webpage_handle(
                url, display_id, note, fatal=fatal, impersonate=True
            )
            if res is False:
                return False

            webpage, urlh = res
            if urllib.parse.urlparse(urlh.url).path == "/login":
                message = "TikTok is requiring login for access to this content"
                if fatal:
                    self.raise_login_required(message)
                self.report_warning(f"{message}. {self._login_hint()}", video_id=display_id)
                return False

            return webpage

        webpage = get_webpage(note="Downloading webpage")
        if webpage is False:
            return None

        universal_data = self._get_universal_data(webpage, display_id)
        if not universal_data:
            try:
                cookie_names = self._solve_challenge_and_set_cookies(webpage)
            except ExtractorError as e:
                if fatal:
                    raise
                self.report_warning(e.orig_msg, video_id=display_id)
                return None

            webpage = get_webpage(note="Downloading webpage with challenge cookie")
            # Manually clear challenge cookies that should expire immediately after webpage request
            for cookie_name in filter(None, cookie_names):
                self.cookiejar.clear(domain=".tiktok.com", path="/", name=cookie_name)
            if webpage is False:
                return None
            universal_data = self._get_universal_data(webpage, display_id)

        if not universal_data:
            message = "Unable to extract universal data for rehydration"
            if fatal:
                raise ExtractorError(message)
            self.report_warning(message, video_id=display_id)
            return None
        return universal_data

    def _entries(self, sec_uid, user_name, fail_early=False):
        display_id = user_name or sec_uid
        seen_ids = set()

        cursor = int(time.time() * self._CURSOR_SCALE)
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
                if current_batch and current_batch == sorted(seen_ids):
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
                author = (
                    traverse_obj(video, ("author", ("uniqueId", "secUid", "id"), {str}, any)) or "_"
                )
                webpage_url = self._create_url(author, video_id)
                yield self.url_result(
                    webpage_url,
                    TikTokIE,
                    **self._parse_aweme_video_web(video, webpage_url, video_id, extract_flat=True),
                )

            cursor = self._get_cursor(response, cursor)
            if not cursor:
                return

            if not traverse_obj(response, (("hasMore", "hasMorePrevious"), {bool}, any)):
                return

            # This code path is ideally only reached when one of the following is true:
            # 1. TikTok profile is private or has likes closed and webpage detection
            #    was bypassed due to a tiktokuser:sec_uid or tiktokliked:sec_uid URL
            # 2. TikTok profile is *not* private but all of their videos are private
            if fail_early and not seen_ids:
                self.raise_login_required(self._FAIL_EARLY_MESSAGE)

    def _get_cursor(self, response, old_cursor):
        cursor = int_or_none(response.get("cursor"))
        if not cursor or old_cursor == cursor:
            # User may not have posted within this ~1 week lookback, so manually adjust cursor
            cursor = old_cursor - 7 * 86_400 * self._CURSOR_SCALE
        # In case 'hasMorePrevious' is wrong, break if we have gone back before TikTok existed
        if cursor < 1472706000 * self._CURSOR_SCALE:
            return None
        return cursor


class TikTokLikedIE(TikTokUserBaseIE):
    IE_NAME = "tiktok:liked"
    _VALID_URL = r"tiktokliked:(?P<username>[\w.-]+)|https?://(?:www\.)?tiktok\.com/@(?P<username2>[\w.-]+)/liked/?"
    _FAIL_EARLY_MESSAGE = (
        "This user's account is likely private, has likes hidden, "
        "or all of their likes are private. "
        "Open likes to the public or log into this account"
    )
    _API_BASE_URL = "https://www.tiktok.com/api/favorite/item_list/"

    def _real_extract(self, url):
        user_name, user_name2 = self._match_valid_url(url).group("username", "username2")
        user_name, sec_uid = user_name or user_name2, None
        if re.fullmatch(r"MS4wLjABAAAA[\w-]{64}", user_name):
            user_name, sec_uid = None, user_name
            fail_early = True
        else:
            fail_early = False
            universal_data = (
                self._extract_universal_data(
                    self._UPLOADER_URL_FORMAT % user_name, user_name, fatal=False
                )
                or {}
            )
            detail = traverse_obj(universal_data, ("webapp.user-detail", {dict})) or {}
            likes_count = traverse_obj(
                detail, ("userInfo", ("stats", "statsV2"), "diggCount", {int_or_none}, any)
            )
            if not likes_count and detail.get("statusCode") == 10222:
                self.raise_login_required(
                    "This user's account is private. Log into an account that has access"
                )
            elif likes_count == 0:
                self.raise_login_required(
                    "This user's liked videos are private. "
                    "Open likes to the public or log into this account",
                )
            sec_uid = traverse_obj(detail, ("userInfo", "user", "secUid", {str}))
            if not sec_uid:
                sec_uid = self._extract_sec_uid_from_embed(user_name)

        if not sec_uid:
            raise ExtractorError(
                "Unable to extract secondary user ID. If you are able to get the channel_id "
                'from a video posted by this user, try using "tiktokliked:channel_id" as the '
                "input URL (replacing `channel_id` with its actual value)",
                expected=True,
            )

        return self.playlist_result(
            self._entries(sec_uid, user_name, fail_early), sec_uid, user_name
        )


class TikTokSavedIE(TikTokUserBaseIE):
    IE_NAME = "tiktok:saved"
    _VALID_URL = r"https?://(?:www\.)?tiktok\.com/saved/?|:tiktoksaved"
    _CURSOR_SCALE = 1  # cursor is in seconds
    _API_BASE_URL = "https://www.tiktok.com/api/user/collect/item_list/"

    def _real_extract(self, _url):
        universal_data = self._extract_universal_data(self._WEBPAGE_HOST, fatal=False) or {}

        user_name = traverse_obj(universal_data, ("webapp.app-context", "user", "uniqueId", {str}))
        sec_uid = traverse_obj(universal_data, ("webapp.app-context", "user", "secUid", {str}))

        if not (user_name or sec_uid):
            self.raise_login_required("You are not logged in. Log into an account that has access")

        return self.playlist_result(
            self._entries(sec_uid, user_name, fail_early=True), sec_uid, user_name
        )


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
    url: str,
    download: bool = False,
    use_cookies: bool = False,
    always_retry: bool = False,
) -> dict[str, any] | list[dict[str, any]]:
    """Выполняет запрос к yt-dlp с обработкой сетевых ошибок.

    :param ydl_opts: Опции для yt-dlp
    :param url: URL для запроса
    :param download: Флаг скачивания
    :param use_cookies: Флаг использования cookies
    :param always_retry: Retry при не сетевых ошибках
    :return: Информация о видео или список видео

    :raises NetworkError: При сетевых ошибках
    :raises Exception: При других ошибках
    """
    if USER_AGENT:
        ydl_opts["http_headers"] = {"User-Agent": USER_AGENT}
    ydl_opts["logger"] = YtDlpLogger(**ydl_opts)

    attempt = 0
    while attempt < MAX_RETRIES:
        if COOKIES_FILE and use_cookies:
            # используем cookies только когда это необходимо
            ydl_opts["cookiefile"] = COOKIES_FILE
        try:
            with yt_dlp.YoutubeDL(ydl_opts.copy()) as ydl:
                match url:  # tmp пока код не замерджили в yt-dlp
                    case url if url.startswith("https://www.tiktok.com/@/video/"):
                        return ydl.extract_info(url, process=download)
                    case url if url.startswith("tiktokliked:"):
                        return TikTokLikedIE(ydl).extract(url)
                    case url if url.startswith(":tiktoksaved"):
                        return TikTokSavedIE(ydl).extract(url)
                    case _:
                        raise ValueError(f"Invalid URL: {url}")
        except Exception as e:
            error_msg = get_error_message(e)
            is_cookies_error = any(err in error_msg for err in COOKIE_ERRORS)
            is_network_error = any(err in str(e) for err in NETWORK_ERRORS)
            is_last_attempt = attempt + 1 >= MAX_RETRIES

            if is_cookies_error and COOKIES_FILE and not use_cookies:
                # если ошибка из-за логина, добавляем cookies и пробуем снова не тратя attempt
                use_cookies = True
                continue

            if (is_network_error or always_retry) and not ydl_opts.get("no_errors"):
                logger.warning(
                    "Error requesting %s (attempt %s/%s): %s",
                    url,
                    attempt + 1,
                    MAX_RETRIES,
                    error_msg,
                )

            if not is_network_error and (is_last_attempt or not always_retry):
                raise e

            attempt += 1

    # Достигли максимального количества сетевых ошибок
    logger.error(
        "Network error detected, skipping\n"
        f"Try to {'change' if USER_AGENT else 'set'} USER_AGENT in settings.conf\n"
        "Check https://github.com/skrepkaq/ATP#useragent for more information"
    )
    raise NetworkError


def check_video_availability(video: Video, no_errors: bool = False) -> VideoInfo | None:
    """Проверяет доступность видео TikTok.

    :param video: Видео
    :param no_errors: Не выводить ошибки

    :return: Информация о видео или None при сетевой ошибке
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "no_errors": no_errors,
    }

    try:
        info = yt_dlp_request(
            ydl_opts,
            url=f"https://www.tiktok.com/@/video/{video.id}",
            always_retry=video.status == VideoStatus.SUCCESS,
        )
        return VideoInfo(
            deleted_reason=None,
            date=datetime.fromtimestamp(info["timestamp"])
            if info.get("timestamp") is not None
            else None,
        )
    except NetworkError:
        return None
    except Exception as e:
        error_msg = get_error_message(e)
        if not no_errors:
            logger.error("Error checking video %s: %s", video.id, error_msg)
        return VideoInfo(deleted_reason=error_msg)


def download_video(video: Video) -> VideoInfo | None:
    """Загружает видео TikTok.

    :param video: Видео

    :return: Информация о видео или None при сетевой ошибке
    """
    ydl_opts = {
        "format": "best",
        "outtmpl": str(Path(DOWNLOADS_DIR) / f"{video.id}.mp4"),
        "quiet": False,
        "no_warnings": False,
    }

    error_msg = None
    try:
        info = yt_dlp_request(
            ydl_opts,
            url=f"https://www.tiktok.com/@/video/{video.id}",
            download=True,
            always_retry=video.status == VideoStatus.NEW,
        )
        if info["format_id"] == "audio":
            success = download_slideshow(video.id)
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
        logger.error("Error downloading video %s: %s", video.id, error_msg)
        return VideoInfo(deleted_reason=error_msg)


def get_user_liked_videos(username: str) -> list[dict]:
    """Получает список видео, которые пользователь отметил как понравившиеся.

    :param username: Имя пользователя

    :return: Список видео
    """
    ydl_opts = {
        "quiet": False,
        "no_warnings": False,
    }

    try:
        info = yt_dlp_request(ydl_opts, url=f"tiktokliked:{username}", use_cookies=True)
        return info.get("entries", [])
    except Exception as e:
        error_msg = get_error_message(e)
        logger.error("Error importing user liked videos: %s", error_msg)
        return []


def get_user_saved_videos(_username: str | None = None) -> list[dict]:
    """Получает список видео, которые пользователь сохранил.

    :param _username: Имя пользователя (не используется, нужен для совместимости с get_liked_videos)

    :return: Список видео
    """
    ydl_opts = {
        "quiet": False,
        "no_warnings": False,
    }

    if not COOKIES_FILE:
        logger.warning("No cookies file found, skipping import saved videos")
        return []

    try:
        info = yt_dlp_request(ydl_opts, url=":tiktoksaved", use_cookies=True)
        return info.get("entries", [])
    except Exception as e:
        error_msg = get_error_message(e)
        logger.error("Error importing user saved videos: %s", error_msg)
        return []


def download_slideshow(video_id: str) -> bool:
    logger.info("Processing slideshow: %s", video_id)

    temp_files_cleanup()

    # Загрузка изображений и аудио
    try:
        job.DownloadJob(f"https://www.tiktok.com/@/photo/{video_id}").run()
    except Exception as e:
        logger.error("Error downloading images for the slideshow: %s", e)
        return False

    # Создание слайдшоу
    return render_slideshow(video_id)
