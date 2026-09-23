"""Drop the redundant UNIQUE constraint on issues_ticket.id.

Migration 001 declared the primary key with ``unique=True``, which created an
extra ``issues_ticket_id_key`` constraint (and index) on top of the primary
key.

Revision ID: c3d5e7f9a1b2
Revises: b7c1d9e2f4a3
Create Date: 2026-09-23 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d5e7f9a1b2"
down_revision = "b7c1d9e2f4a3"
branch_labels = None
depends_on = None

_CONSTRAINT = "issues_ticket_id_key"


def upgrade():
    op.execute(f"ALTER TABLE issues_ticket DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")


def downgrade():
    op.create_unique_constraint(_CONSTRAINT, "issues_ticket", ["id"])
