"""remove source column

Revision ID: 006
Create Date: 2025-05-29

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("videos", "source")


def downgrade():
    op.add_column("videos", sa.Column("source", sa.String(), nullable=True))
