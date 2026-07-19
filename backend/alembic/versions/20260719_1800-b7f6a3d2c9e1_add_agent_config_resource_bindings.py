"""add agent config resource bindings

Revision ID: b7f6a3d2c9e1
Revises: 4a19c8e2d7b5
Create Date: 2026-07-19 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7f6a3d2c9e1"
down_revision: Union[str, Sequence[str], None] = "4a19c8e2d7b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "agent_configs",
        sa.Column(
            "tool_ids",
            sa.JSON(),
            nullable=True,
            server_default="[]",
            comment="Explicit tool bindings for agent config",
        ),
    )
    op.add_column(
        "agent_configs",
        sa.Column(
            "mcp_server_ids",
            sa.JSON(),
            nullable=True,
            server_default="[]",
            comment="Explicit MCP server bindings for agent config",
        ),
    )
    op.execute("UPDATE agent_configs SET tool_ids = '[]' WHERE tool_ids IS NULL")
    op.execute("UPDATE agent_configs SET mcp_server_ids = '[]' WHERE mcp_server_ids IS NULL")
    with op.batch_alter_table("agent_configs", schema=None) as batch_op:
        batch_op.alter_column(
            "tool_ids",
            existing_type=sa.JSON(),
            nullable=False,
            server_default="[]",
        )
        batch_op.alter_column(
            "mcp_server_ids",
            existing_type=sa.JSON(),
            nullable=False,
            server_default="[]",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_configs", schema=None) as batch_op:
        batch_op.drop_column("mcp_server_ids")
        batch_op.drop_column("tool_ids")
