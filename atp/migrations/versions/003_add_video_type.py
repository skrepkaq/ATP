"""add video type column

Revision ID: 003
Create Date: 2025-04-20

"""

from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.schema import MetaData

from atp.settings import DOWNLOADS_DIR

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


# Use isolated MetaData so it doesn't conflict with global one
metadata = MetaData()
Base = declarative_base(metadata=metadata)


class TempVideo(Base):
    """
    Временная модель для миграции данных.
    """

    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    type = Column(String, nullable=True)
    status = Column(String, nullable=False, default="new")
    updated_at = Column(DateTime, default=lambda: datetime.now(), onupdate=lambda: datetime.now())


def upgrade():
    op.add_column("videos", sa.Column("type", sa.String(), nullable=True))

    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        for video in (
            session.query(TempVideo).filter(TempVideo.status.in_(("success", "deleted"))).all()
        ):
            slideshow_path = Path(DOWNLOADS_DIR) / f"{video.id}_slideshow.mp4"

            if slideshow_path.exists():
                video.type = "slideshow"
                slideshow_path.rename(Path(DOWNLOADS_DIR) / f"{video.id}.mp4")
            else:
                video.type = "video"

        session.commit()
    except Exception as e:
        session.rollback()
        print(f"Error updating video types: {e}")
    finally:
        session.close()


def downgrade():
    op.drop_column("videos", "type")
