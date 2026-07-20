"""Establish migration lineage without creating any business schema.

Revision ID: 0001_empty_baseline
Revises: None
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

revision: str = "0001_empty_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Establish the empty baseline without creating schema objects."""
    return None


def downgrade() -> None:
    """Remove no schema objects because the baseline is empty."""
    return None
