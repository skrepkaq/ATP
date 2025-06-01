"""add author column

Revision ID: 004
Create Date: 2025-05-08

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("author", sa.String(), nullable=True))


def downgrade():
    op.drop_column("videos", "author")
