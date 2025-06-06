"""
Модуль для отправки уведомлений в Telegram
"""

import io
import json
import os

import requests

from atp.models import Video
from atp.settings import DOWNLOADS_DIR, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_video_deleted_notification(video: Video) -> bool:
    """Отправляет уведомление в Telegram о видео, удалённом из TikTok.

    :param video: Объект видео из базы данных

    :return: True если сообщение отправлено, False иначе
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram parameters not configured (token or chat ID)")
        return False

    video_path = os.path.join(DOWNLOADS_DIR, f"{video.id}.mp4")
    if not os.path.exists(video_path):
        print(f"Error: video file not found: {video_path}")
        return False

    try:
        with open(video_path, "rb") as video_file:
            files = {"video": video_file}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": (
                    f"{video.author + '\n' if video.author else ''}"
                    f"{video.name}\n{video.date.strftime('%d.%m.%Y')}"
                ),
                "supports_streaming": True,
            }
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
            response = requests.post(url, data=data, files=files)

        if response.status_code == 200:
            print("Telegram notification sent successfully.")
            message_id = response.json().get('result', {}).get('message_id')
            return message_id
        else:
            print(f"Failed to send Telegram notification: {response.text}")
            return False

    except Exception as e:
        print(f"Exception occurred while sending Telegram notification: {e}")
        return False


def send_message(text: str) -> bool:
    """Отправляет сообщение в Telegram.

    :param text: Текст сообщения для отправки

    :return: True если сообщение отправлено, False иначе
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram parameters not configured (token or chat ID)")
        return False

    try:
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
        }
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        response = requests.post(url, data=data)

        if response.status_code == 200:
            print("Telegram message sent successfully.")
            return True
        else:
            print(f"Failed to send Telegram message: {response.text}")
            return False

    except Exception as e:
        print(f"Exception occurred while sending Telegram message: {e}")
        return False


def handle_video_restoration(video: Video) -> bool:
    """Заменяет видео в сообщении на пустой файл.
    Telegram не даёт удалить сообщение старше 48 часов, поэтому заменяем видео на пустой файл.

    :param video: Объект видео из базы данных

    :return: True если сообщение отредактировано, False иначе
    """

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram parameters not configured (token or chat ID)")
        return False

    try:
        file_name = 'restored'

        media = {
            "type": "document",
            "media": f"attach://{file_name}",
        }

        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": video.message_id,
            "media": json.dumps(media)
        }

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageMedia"
        response = requests.post(url, data=payload, files={file_name: (file_name, io.BytesIO(video.id.encode()))})

        if response.status_code == 200:
            print("Telegram message caption edited successfully.")
            return True
        else:
            print(f"Failed to edit Telegram message caption: {response.text}")
            return False

    except Exception as e:
        print(f"Exception occurred while editing message caption: {e}")
        return False
