"""Add enterprise features: callback_url, extracted_metadata, quality_score, quality_issues

Revision ID: 003_add_enterprise_features
Revises: 002_add_confidence_and_guess
Create Date: 2026-09-25 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "003_add_enterprise_features"
down_revision: Union[str, None] = "002_add_confidence_and_guess"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("callback_url", sa.String(length=512), nullable=True))
    op.add_column("documents", sa.Column("extracted_metadata", sa.JSON(), nullable=True))
    op.add_column("documents", sa.Column("quality_score", sa.Integer(), nullable=True))
    op.add_column("documents", sa.Column("quality_issues", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "quality_issues")
    op.drop_column("documents", "quality_score")
    op.drop_column("documents", "extracted_metadata")
    op.drop_column("documents", "callback_url")
