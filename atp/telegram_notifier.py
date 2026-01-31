"""
Модуль для отправки уведомлений в Telegram
"""

import io
import json
import random
from pathlib import Path

import requests

from atp import settings
from atp.config_init import set_config_value
from atp.models import Video


def send_video_deleted_notification(video: Video) -> bool:
    """Отправляет уведомление в Telegram о видео, удалённом из TikTok.

    :param video: Объект видео из базы данных

    :return: True если сообщение отправлено, False иначе
    """
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        print("Error: Telegram parameters not configured (token or chat ID)")
        return False

    video_path = Path(settings.DOWNLOADS_DIR) / f"{video.id}.mp4"
    if not video_path.exists():
        print(f"Error: video file not found: {video_path}")
        return False

    try:
        with open(video_path, "rb") as video_file:
            MAX_LENGHT = 1024
            author = video.author + "\n" if video.author else ""
            cut_name = video.name or ""
            total_length = len(author) + len(cut_name) + 11
            if total_length > MAX_LENGHT:
                diff = total_length - MAX_LENGHT
                cut_name = cut_name[: -diff - 3] + "..."
            files = {"video": video_file}
            data = {
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "caption": author + cut_name + "\n" + video.date.strftime("%d.%m.%Y"),
                "supports_streaming": True,
            }
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendVideo"
            response = requests.post(url, data=data, files=files, timeout=60)

        if response.status_code == 200:
            print("Telegram notification sent successfully.")
            message_id = response.json().get("result", {}).get("message_id")
            return message_id
        else:
            print(f"Failed to send Telegram notification: {response.text}")
            return False

    except Exception as e:
        print(f"Exception occurred while sending Telegram notification: {e}")
        return False


def handle_video_restoration(video: Video) -> bool:
    """Заменяет видео в сообщении на BMP картинку.
    Telegram не даёт удалить сообщение старше 48 часов, поэтому заменяем видео на BMP файл.

    :param video: Объект видео из базы данных

    :return: True если сообщение отредактировано, False иначе
    """

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        print("Error: Telegram parameters not configured (token or chat ID)")
        return False

    try:
        random.seed(video.id)
        color = [0, random.randint(0, 255), 255]
        random.shuffle(color)

        base_bmp_hex = "424d1e000000000000001a0000000c0000000100010001001800"
        bmp_data = bytes.fromhex(base_bmp_hex) + bytes(color) + b"\x00"
        file_name = "restored"

        media = {
            "type": "photo",
            "media": f"attach://{file_name}",
            "parse_mode": "Markdown",
            "caption": f"[Видео](https://tiktok.com/@/video/{video.id}) было восстановлено!",
        }

        payload = {
            "chat_id": settings.TELEGRAM_CHAT_ID,
            "message_id": video.message_id,
            "media": json.dumps(media),
        }

        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/editMessageMedia"
        response = requests.post(
            url,
            data=payload,
            files={file_name: (file_name, io.BytesIO(bmp_data))},
            timeout=60,
        )

        if response.status_code == 200:
            print("Telegram message media edited successfully.")
            return True
        else:
            print(f"Failed to edit Telegram message media: {response.text}")
            return False

    except Exception as e:
        print(f"Exception occurred while editing message media: {e}")
        return False


def get_telegram_chat_id() -> None:
    """Получает ID чата в Telegram и сохраняет его в settings.conf"""
    if not settings.TELEGRAM_BOT_TOKEN or settings.TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates"
        response = requests.get(url, timeout=60)
        if response.status_code != 200:
            print(f"Failed to get Telegram chat ID: {response.text}")
            return
        for event in response.json()["result"][::-1]:
            if event_message := (
                event.get("message") or event.get("channel_post") or event.get("my_chat_member")
            ):
                chat = event_message["chat"]
                chat_id = str(chat["id"])
                title = chat.get("title") or chat.get("username")
                print(f"Found chat {title} with ID {chat_id}")
                settings.TELEGRAM_CHAT_ID = chat_id
                set_config_value("TELEGRAM_CHAT_ID", chat_id)
                break
        else:
            print("Can't find chat ID, try sending any message to a channel")
            return
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(
            url,
            data={"chat_id": chat_id, "text": "Удаленные видео будут публиковаться в этом чате"},
            timeout=60,
        )
        if response.status_code == 200:
            print("Message sent successfully.")
        else:
            print(
                f"Failed to send message to chat {title} with ID {chat_id}. Check bot permissions."
            )
            settings.TELEGRAM_CHAT_ID = None
            set_config_value("TELEGRAM_CHAT_ID", "")

    except Exception as e:
        print(f"Error occurred while getting Telegram chat ID: {e}")
        settings.TELEGRAM_CHAT_ID = None
        set_config_value("TELEGRAM_CHAT_ID", "")
