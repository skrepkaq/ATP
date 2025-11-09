"""add message id column

Revision ID: 007
Create Date: 2025-06-04

"""

import json
import os

import sqlalchemy as sa
from alembic import op
from sqlalchemy.orm import Session

from atp import crud

# revision identifiers, used by Alembic.
revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def load_messages():
    TELEGRAM_MESSAGES_FILE = "./result.json"
    if not os.path.exists(TELEGRAM_MESSAGES_FILE):
        print(f"File {TELEGRAM_MESSAGES_FILE} does not exist")
        return []
    with open(TELEGRAM_MESSAGES_FILE) as f:
        data = json.load(f)
        messages = []
        for message in data["messages"]:
            if message.get("type") == "message":
                message_text = "".join(
                    entity.get("text", "") for entity in message["text_entities"]
                )
                lines = message_text.strip().split("\n")
                if len(lines) >= 1:
                    video_name = lines[1] if len(lines) >= 3 else lines[0]
                    if not video_name:
                        continue
                    messages.append({"id": message["id"], "text": video_name})
        return messages


def upgrade():
    op.add_column("videos", sa.Column("message_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    session = Session(bind=bind)

    if not (videos := crud.get_all_videos(session, status="deleted")):
        return

    messages = load_messages()

    for message in messages:
        matched_videos = [
            video
            for video in videos
            if (video.name.strip() if video.name else "") == message["text"].strip()
        ]
        if len(matched_videos) == 1:
            print(f"Found message {message['id']} for video {matched_videos[0].name}")
            matched_videos[0].message_id = message["id"]
            session.commit()
        else:
            print(f"Found {len(matched_videos)} videos for message {message['id']}")


def downgrade():
    op.drop_column("videos", "message_id")
