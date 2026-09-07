"""Make issues_ticket.assignee_id ON DELETE SET NULL.

Previously deleting a user cascaded (via the ORM backref) into deleting every
ticket they were assigned to. Tickets must survive an assignee being removed —
they just get unassigned.

Revision ID: b7c1d9e2f4a3
Revises: e4b6d8f7a9c1
Create Date: 2026-09-07 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c1d9e2f4a3"
down_revision = "e4b6d8f7a9c1"
branch_labels = None
depends_on = None

_CONSTRAINT = "issues_ticket_assignee_id_fkey"


def upgrade():
    op.drop_constraint(_CONSTRAINT, "issues_ticket", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "issues_ticket",
        "user",
        ["assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(_CONSTRAINT, "issues_ticket", type_="foreignkey")
    op.create_foreign_key(
        _CONSTRAINT,
        "issues_ticket",
        "user",
        ["assignee_id"],
        ["id"],
    )
