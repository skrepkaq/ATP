"""
Модуль для работы с yt-dlp и загрузки видео из TikTok.

Этот модуль предоставляет функции для:
- Загрузки видео с помощью yt-dlp
- Проверки доступности видео
- Обработки сетевых ошибок
- Обновления информации о видео в базе данных
"""

import itertools
import re
from datetime import datetime
from pathlib import Path

import yt_dlp
from sqlalchemy.orm import Session
from yt_dlp.extractor.tiktok import TikTokIE, TikTokUserIE
from yt_dlp.utils import ExtractorError, traverse_obj

from atp.models import Video
from atp.settings import ANTI_BOT_BYPASS, DOWNLOADS_DIR, MAX_RETRIES
from atp.slideshow import download_slideshow


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

            if detail.get("statusCode") == 10222:
                self.raise_login_required(
                    "This user's account is private. Log into an account that has access"
                )

            sec_uid = traverse_obj(detail, ("userInfo", "user", "secUid", {str}))
            if not sec_uid:
                sec_uid = self._extract_sec_uid_from_embed(user_name)

        if not sec_uid:
            raise ExtractorError(
                "Unable to extract secondary user ID. If you are able to get the channel_id "
                'from a video posted by this user, try using "tiktokliked:channel_id/liked" as the '
                "input URL (replacing `channel_id` with its actual value)",
                expected=True,
            )

        if not traverse_obj(detail, ("userInfo", "user", "openFavorite", {bool})):
            raise ExtractorError(
                "This user's liked videos are not open to the public. "
                "Open it or log into this account",
                expected=True,
            )

        return self.playlist_result(self._entries(sec_uid, user_name), sec_uid, user_name)


class NetworkError(Exception):
    """Исключение при сетевых ошибках."""

    pass


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
    ]
    if ANTI_BOT_BYPASS:
        ydl_opts["http_headers"] = {
            "User-Agent": "hi mom!"
        }  # передаём привет маме создателя анти-бот защиты (хз как, но пока это работает)

    is_network_error = False
    exc = None
    for attempt in range(MAX_RETRIES):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                if video_id:
                    return ydl.extract_info(f"https://www.tiktok.com/@/video/{video_id}/", download)
                elif username:
                    return TikTokLikedIE(ydl).extract(f"tiktokliked:{username}/liked")
        except Exception as e:
            exc = e
            error_msg = str(e)
            print(
                f"Error checking {'video' if video_id else 'user'} {video_id or username} "
                f"attempt {attempt + 1}/{MAX_RETRIES}): {e}"
            )

            is_network_error = any(err in error_msg for err in network_errors)

    # Если достигли максимального количества попыток или не сетевая ошибка
    if is_network_error:
        print(
            "Network error detected, skipping\n"
            f"Try to {'disable' if ANTI_BOT_BYPASS else 'enable'} ANTI_BOT_BYPASS in settings.conf"
        )
        raise NetworkError
    else:
        raise exc


def download_video(db: Session, video_id: str) -> bool | None:
    """Загружает видео TikTok.

    :param db: Сессия базы данных
    :param video_id: ID видео

    :return: True если загрузка успешна, False в противном случае, None при сетевой ошибке
    """
    ydl_opts = {
        "format": "best",
        "outtmpl": str(Path(DOWNLOADS_DIR) / f"{video_id}.mp4"),
        "quiet": False,
        "no_warnings": False,
    }

    try:
        info = yt_dlp_request(ydl_opts, video_id=video_id, download=True)
    except NetworkError:
        return None
    except Exception as e:
        print(f"Error downloading video {video_id}: {e}")
        info = False

    video: Video = db.query(Video).filter(Video.id == video_id).first()
    if video:
        video.status = "success" if info else "failed"
        video.name = info.get("description", f"Video {video_id}") if info else ""
        video.last_checked = datetime.now()
        video.type = "video"  # Устанавливаем тип по умолчанию как "video"

        # Если в видео есть информация об авторе и она отсутствует в базе
        if info and info.get("uploader") and not video.author:
            video.author = info["uploader"]

        db.commit()

        if info and info["format_id"] == "audio":
            if download_slideshow(video_id):
                video.type = "slideshow"
            else:
                video.status = "new"
                info = False
            db.commit()
    return bool(info)


def check_video_availability(video_id: str) -> bool:
    """Проверяет доступность видео TikTok.

    :param video_id: ID видео

    :return: True если видео доступно, False в противном случае

    :raises NetworkError: При сетевых ошибках
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
    }

    try:
        yt_dlp_request(ydl_opts, video_id=video_id, download=False)
        return True
    except NetworkError as e:
        raise NetworkError from e
    except Exception:
        return False


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
