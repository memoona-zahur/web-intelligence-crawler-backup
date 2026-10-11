"""Duplicate-by-redirect marker on websites (CR-B05).

Revision ID: 0003_duplicate_of
Revises: 0002_phase2_crawl_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_duplicate_of"
down_revision = "0002_phase2_crawl_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "duplicate_of_id" not in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("websites")}:
        op.add_column("websites", sa.Column("duplicate_of_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    pass  # SQLite cannot drop a column without rebuilding the table; the column is harmless