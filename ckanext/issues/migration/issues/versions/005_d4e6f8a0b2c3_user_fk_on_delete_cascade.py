"""Make ticket/message author FKs ON DELETE CASCADE.

The ORM already deletes a user's tickets with them, but the database did
not, and nothing handled their replies on other users' tickets: purging such
a user failed with an IntegrityError.

Revision ID: d4e6f8a0b2c3
Revises: c3d5e7f9a1b2
Create Date: 2026-09-23 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "d4e6f8a0b2c3"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None

_FKS = [
    ("issues_ticket", "issues_ticket_author_id_fkey"),
    ("issues_ticket_message", "issues_ticket_message_author_id_fkey"),
]


def _recreate(ondelete: str | None) -> None:
    for table, constraint in _FKS:
        op.drop_constraint(constraint, table, type_="foreignkey")
        op.create_foreign_key(constraint, table, "user", ["author_id"], ["id"], ondelete=ondelete)


def upgrade():
    _recreate("CASCADE")


def downgrade():
    _recreate(None)
