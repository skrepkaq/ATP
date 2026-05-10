"""add liked and saved columns

Revision ID: 010
Revises: 009
Create Date: 2026-04-04 14:43:50.601669

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "videos",
        sa.Column("liked", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "videos",
        sa.Column("saved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("videos", "saved")
    op.drop_column("videos", "liked")
