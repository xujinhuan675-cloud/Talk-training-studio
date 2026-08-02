"""rename and make competency outcome rating nullable

Revision ID: b3d7e9a1c5f2
Revises: a8c4e2f6b1d9
Create Date: 2026-08-02 09:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3d7e9a1c5f2"
down_revision: Union[str, Sequence[str], None] = "a8c4e2f6b1d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("stakeholder_competency_evaluations") as batch_op:
        batch_op.alter_column(
            "overall_score",
            new_column_name="outcome_rating",
            existing_type=sa.Float(),
            nullable=True,
        )


def downgrade() -> None:
    null_count = op.get_bind().execute(
        sa.text(
            "SELECT COUNT(*) FROM stakeholder_competency_evaluations "
            "WHERE outcome_rating IS NULL"
        )
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            "Cannot downgrade while evidence-insufficient evaluations have no outcome rating"
        )
    with op.batch_alter_table("stakeholder_competency_evaluations") as batch_op:
        batch_op.alter_column(
            "outcome_rating",
            new_column_name="overall_score",
            existing_type=sa.Float(),
            nullable=False,
        )
