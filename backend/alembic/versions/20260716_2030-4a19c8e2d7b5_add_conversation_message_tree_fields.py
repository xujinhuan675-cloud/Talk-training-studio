"""add conversation message tree fields

Revision ID: 4a19c8e2d7b5
Revises: 8d3e91f4a2b0
Create Date: 2026-07-16 20:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4a19c8e2d7b5"
down_revision: Union[str, Sequence[str], None] = "8d3e91f4a2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "messages",
        sa.Column(
            "public_id",
            sa.String(length=64),
            nullable=True,
            comment="Stable public message ID used by message tree clients",
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "parent_message_id",
            sa.String(length=64),
            nullable=True,
            comment="Parent public message ID for tree/branch traversal",
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "branch_id",
            sa.String(length=64),
            nullable=True,
            server_default="main",
            comment="Conversation branch identifier",
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
            comment="Message lifecycle status",
        ),
    )
    op.add_column(
        "messages",
        sa.Column("finish_reason", sa.String(length=100), nullable=True, comment="LLM finish reason"),
    )
    op.add_column(
        "messages",
        sa.Column("provider", sa.String(length=100), nullable=True, comment="LLM provider"),
    )
    op.add_column(
        "messages",
        sa.Column("model", sa.String(length=100), nullable=True, comment="LLM model"),
    )
    op.add_column(
        "messages",
        sa.Column(
            "content_parts",
            sa.JSON(),
            nullable=True,
            comment="Structured content parts for multimodal/tool-aware messages",
        ),
    )
    op.execute(
        "UPDATE messages "
        "SET public_id = 'msg_legacy_' || CAST(id AS TEXT) "
        "WHERE public_id IS NULL"
    )
    op.alter_column("messages", "public_id", existing_type=sa.String(length=64), nullable=False)
    op.create_index("ix_messages_public_id", "messages", ["public_id"], unique=True)
    op.create_index("ix_messages_parent_message_id", "messages", ["parent_message_id"])
    op.create_index(
        "ix_messages_conversation_branch",
        "messages",
        ["conversation_id", "branch_id", "created_at"],
    )

    op.add_column(
        "runs",
        sa.Column("public_id", sa.String(length=64), nullable=True, comment="Stable public run ID"),
    )
    op.add_column(
        "runs",
        sa.Column("provider", sa.String(length=100), nullable=True, comment="LLM provider"),
    )
    op.add_column(
        "runs",
        sa.Column("finish_reason", sa.String(length=100), nullable=True, comment="LLM finish reason"),
    )
    op.add_column(
        "runs",
        sa.Column("metadata", sa.JSON(), nullable=True, comment="Structured run metadata"),
    )
    op.execute(
        "UPDATE runs "
        "SET public_id = 'run_legacy_' || CAST(id AS TEXT) "
        "WHERE public_id IS NULL"
    )
    op.alter_column("runs", "public_id", existing_type=sa.String(length=64), nullable=False)
    op.create_index("ix_runs_public_id", "runs", ["public_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_runs_public_id", table_name="runs")
    op.drop_column("runs", "metadata")
    op.drop_column("runs", "finish_reason")
    op.drop_column("runs", "provider")
    op.drop_column("runs", "public_id")

    op.drop_index("ix_messages_conversation_branch", table_name="messages")
    op.drop_index("ix_messages_parent_message_id", table_name="messages")
    op.drop_index("ix_messages_public_id", table_name="messages")
    op.drop_column("messages", "content_parts")
    op.drop_column("messages", "model")
    op.drop_column("messages", "provider")
    op.drop_column("messages", "finish_reason")
    op.drop_column("messages", "status")
    op.drop_column("messages", "branch_id")
    op.drop_column("messages", "parent_message_id")
    op.drop_column("messages", "public_id")
