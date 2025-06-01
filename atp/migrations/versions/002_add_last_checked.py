"""add last_checked

Revision ID: 002
Create Date: 2025-04-15

"""

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("last_checked", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("videos", "last_checked")
