"""Add confidence_score and guess to documents

Revision ID: 002_add_confidence_and_guess
Revises: 001_initial_schema
Create Date: 2026-09-25 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_add_confidence_and_guess"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("confidence_score", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("guess", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "guess")
    op.drop_column("documents", "confidence_score")
