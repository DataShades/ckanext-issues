"""Index issues_ticket_message.ticket_id.

The support queue looks up the latest message of every ticket to count and
list the ones that need a reply; without the index each lookup scans the whole
message table.

Revision ID: e5f7a9b1c3d4
Revises: d4e6f8a0b2c3
Create Date: 2026-11-02 00:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "e5f7a9b1c3d4"
down_revision = "d4e6f8a0b2c3"
branch_labels = None
depends_on = None

_INDEX = "ix_issues_ticket_message_ticket_id"


def upgrade():
    op.create_index(_INDEX, "issues_ticket_message", ["ticket_id"])


def downgrade():
    op.drop_index(_INDEX, table_name="issues_ticket_message")
