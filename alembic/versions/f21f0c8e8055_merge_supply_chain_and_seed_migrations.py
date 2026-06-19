# ruff: noqa
"""merge supply chain and seed migrations.

Revision ID: f21f0c8e8055
Revises: 995910d372dd, a1b2c3d4e5f6
Create Date: 2026-06-19 04:54:28.153734
"""

from typing import Sequence, Union

import sqlmodel  # noqa: F401
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f21f0c8e8055"
down_revision: Union[str, Sequence[str], None] = ("995910d372dd", "a1b2c3d4e5f6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
