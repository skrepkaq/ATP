"""add deleted reason column

Revision ID: 008
Create Date: 2026-02-04

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("deleted_reason", sa.String(), nullable=True))


def downgrade():
    op.drop_column("videos", "deleted_reason")
