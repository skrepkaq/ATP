"""
Модуль для отправки уведомлений в Telegram
"""

import os

import requests

from atp.models import Video
from atp.settings import DOWNLOADS_DIR, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


def send_video_deleted_notification(video: Video) -> bool:
    """Отправляет уведомление в Telegram о видео, которое было удалено из TikTok.

    :param video: Объект видео из базы данных

    :return: True если сообщение было успешно отправлено, False в противном случае
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
                "caption": f"{video.author + '\n' if video.author else ''}{video.name}\n{video.date.strftime('%d.%m.%Y')}",
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

    :return: True если сообщение было успешно отправлено, False в противном случае
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


def delete_message(message_id: int) -> bool:
    """Удаляет сообщение из Telegram.

    :param message_id: ID сообщения для удаления

    :return: True если сообщение было успешно удалено, False в противном случае
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram parameters not configured (token or chat ID)")
        return False

    try:
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "message_id": message_id,
        }
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
        response = requests.post(url, data=data)

        if response.status_code == 200:
            print("Telegram message deleted successfully.")
            return True
        else:
            print(f"Failed to delete Telegram message: {response.text}")
            return False

    except Exception as e:
        print(f"Exception occurred while deleting Telegram message: {e}")
        return False
