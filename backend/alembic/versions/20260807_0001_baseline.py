"""建立 Alembic 迁移基线

Revision ID: 20260807_0001
Revises:
Create Date: 2026-08-07
"""

from typing import Sequence, Union

revision: str = "20260807_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """建立迁移基线；业务表将在后续迁移中创建。"""
    pass


def downgrade() -> None:
    """移除迁移基线。"""
    pass
