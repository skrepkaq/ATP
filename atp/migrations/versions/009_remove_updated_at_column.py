"""remove updated_at column

Revision ID: 009
Revises: 008
Create Date: 2026-03-12 21:35:37.233395

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, DateTime, String
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.schema import MetaData

# Use isolated MetaData so it doesn't conflict with global one
metadata = MetaData()
Base = declarative_base(metadata=metadata)


class TempVideo(Base):
    """
    Временная модель для миграции данных.
    """

    __tablename__ = "videos"

    id = Column(String, primary_key=True)
    updated_at = Column(DateTime, nullable=True)
    last_checked = Column(DateTime, nullable=True)


# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("videos", "updated_at")


def downgrade():
    op.add_column("videos", sa.Column("updated_at", sa.DateTime(), nullable=True))
    bind = op.get_bind()
    session = Session(bind=bind)

    for video in session.query(TempVideo).all():
        video.updated_at = video.last_checked

    session.commit()
