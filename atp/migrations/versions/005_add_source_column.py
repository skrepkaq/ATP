"""add source column

Revision ID: 005
Create Date: 2025-05-07

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("videos", sa.Column("source", sa.String(), nullable=True))


def downgrade():
    op.drop_column("videos", "source")
