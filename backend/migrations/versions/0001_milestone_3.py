"""The tables as milestone 3 created them: categories, recipes, recipe_sources.

Milestone 3 created its tables without migrations (Base.metadata.create_all). This script
creates the same tables, statement for statement, so a milestone-3 database can be
marked as being at this revision and upgraded from here.
tests/test_migrations.py compares the result with tests/fixtures/milestone3_schema.sql.

Revision ID: 0001
Previous: none
Created: 2026-10-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The constraints are listed in the order milestone 3 wrote them.
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "parent_id"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
    )
    op.create_table(
        "recipes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("subcategory_id", sa.Integer(), nullable=True),
        sa.Column("servings", sa.String(), nullable=True),
        sa.Column("ingredient_groups", sa.JSON(), nullable=False),
        sa.Column("step_groups", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("is_sample", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["subcategory_id", "category_id"], ["categories.id", "categories.parent_id"]),
        sa.CheckConstraint("subcategory_id IS NULL OR category_id IS NOT NULL", name="subcategory_needs_category"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
    )
    op.create_table(
        "recipe_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("url", sa.String(), nullable=True),
        sa.Column("creators", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipes.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("recipe_sources")
    op.drop_table("recipes")
    op.drop_table("categories")
