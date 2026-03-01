import io
import json
import logging

import requests

from atp import settings

logger = logging.getLogger(__name__)


def send_media(
    caption: str,
    video: io.BytesIO | None = None,
    photos: list[io.BytesIO] | None = None,
) -> dict:
    """Отправляет медиа в Telegram (видео или фото).

    :param caption: Подпись к медиа
    :param video: Путь к видео файлу (Path) или список путей для медиа-группы
    :param photos: Список фото в виде BytesIO
    :return: Результат ответа от Telegram API (dict)
    :raises: Exception с текстом ответа при ошибке
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        raise Exception("Telegram parameters not configured (token or chat ID)")

    base_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"
    chat_id = settings.TELEGRAM_CHAT_ID

    if video:
        media_type = "video"
        media_items = [video]
    elif photos:
        media_type = "photo"
        media_items = photos
    else:
        raise ValueError("Either video or photos must be provided")

    if len(media_items) > 1:
        files = {}
        media = []
        for i, item in enumerate(media_items):
            key = f"{media_type}{i}"
            files[key] = item
            media.append({"type": media_type, "media": f"attach://{key}"})

        media[0]["caption"] = caption
        data = {"chat_id": chat_id, "media": json.dumps(media)}
        url = f"{base_url}/sendMediaGroup"
    else:
        files = {media_type: media_items[0]}
        data = {"chat_id": chat_id, "caption": caption}
        if media_type == "video":
            data["supports_streaming"] = True
        url = f"{base_url}/send{media_type.capitalize()}"

    response = requests.post(url, data=data, files=files, timeout=180)

    if response.status_code != 200:
        raise Exception(f"Failed to send Telegram media: {response.text}")

    return response.json()["result"]


def edit_media(
    message_id: int,
    caption: str,
    video: io.BytesIO | None = None,
    photo: io.BytesIO | None = None,
    parse_mode: str | None = None,
) -> bool:
    """Редактирует медиа в сообщении Telegram.

    :param message_id: ID сообщения для редактирования
    :param caption: Новая подпись к медиа
    :param video: Видео в виде BytesIO
    :param photo: Фото в виде BytesIO
    :param parse_mode: Режим парсинга (например, "Markdown")
    :return: True если успешно, False иначе
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        logger.error("Error: Telegram parameters not configured (token or chat ID)")
        return False

    if not video and not photo:
        logger.error("Error: Either video or photo must be provided")
        return False

    try:
        media_type = "video" if video else "photo"
        file_obj = video if video else photo

        media = {
            "type": media_type,
            "media": f"attach://{media_type}",
            "caption": caption,
        }
        if parse_mode:
            media["parse_mode"] = parse_mode

        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "message_id": message_id,
            "media": json.dumps(media),
        }

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageMedia"
        response = requests.post(
            url,
            data=payload,
            files={media_type: file_obj},
            timeout=180,
        )

        if response.status_code == 200:
            logger.info("Telegram message media edited successfully.")
            return True
        else:
            logger.error("Failed to edit Telegram message media: %s", response.text)
            return False

    except Exception as e:
        logger.exception("Exception occurred while editing message media: %s", e)
        return False


def discover_chat_id() -> None:
    """Получает ID чата в Telegram и сохраняет его в settings.conf"""
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            logger.error("Failed to get Telegram chat ID: %s", response.text)
            return
        for event in response.json()["result"][::-1]:
            if event_message := (
                event.get("message") or event.get("channel_post") or event.get("my_chat_member")
            ):
                chat = event_message["chat"]
                chat_id = str(chat["id"])
                title = chat.get("title") or chat.get("username")
                logger.info("Found chat %s with ID %s", title, chat_id)

                settings.TELEGRAM_CHAT_ID = chat_id
                settings.set_config_value("TELEGRAM_CHAT_ID", chat_id)
                break
        else:
            logger.warning("Can't find chat ID, try sending any message to a channel")
            return

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": "Удаленные видео будут публиковаться в этом чате"},
            timeout=60,
        )
        if response.status_code == 200:
            logger.info("Message sent successfully.")
        else:
            logger.error(
                f"Failed to send message to chat {title} with ID {chat_id}. Check bot permissions."
            )
            settings.TELEGRAM_CHAT_ID = None
            settings.set_config_value("TELEGRAM_CHAT_ID", "")

    except Exception as e:
        logger.exception("Error occurred while getting Telegram chat ID: %s", e)
        settings.TELEGRAM_CHAT_ID = None
        settings.set_config_value("TELEGRAM_CHAT_ID", "")
