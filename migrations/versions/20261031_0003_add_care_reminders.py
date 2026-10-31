"""add owner care reminders

Revision ID: 20261031_0003
Revises: 20261028_0002
Create Date: 2026-10-31

This migration is prepared for review. It must not be applied to the formal
Supabase database until the owner explicitly approves the schema change.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261031_0003"
down_revision: Union[str, None] = "20261028_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "care_reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pet_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recurrence", sa.String(length=20), nullable=False, server_default="NONE"),
        sa.Column("advance_minutes", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["pet_id"], ["pets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_reminders_pet_id", "care_reminders", ["pet_id"])
    op.create_index("ix_care_reminders_owner_id", "care_reminders", ["owner_id"])
    op.create_index("ix_care_reminders_category", "care_reminders", ["category"])
    op.create_index("ix_care_reminders_scheduled_at", "care_reminders", ["scheduled_at"])
    op.create_index("ix_care_reminders_completed", "care_reminders", ["completed"])
    op.create_index("ix_care_reminder_pet_scheduled", "care_reminders", ["pet_id", "scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_care_reminder_pet_scheduled", table_name="care_reminders")
    op.drop_index("ix_care_reminders_completed", table_name="care_reminders")
    op.drop_index("ix_care_reminders_scheduled_at", table_name="care_reminders")
    op.drop_index("ix_care_reminders_category", table_name="care_reminders")
    op.drop_index("ix_care_reminders_owner_id", table_name="care_reminders")
    op.drop_index("ix_care_reminders_pet_id", table_name="care_reminders")
    op.drop_table("care_reminders")
