from __future__ import annotations

from sqlalchemy import func, select, sql
from sqlalchemy.orm import aliased

import ckan.plugins.toolkit as tk
from ckan import model as ckan_model
from ckan import types

import ckanext.tables.shared as t

from ckanext.issues import formatters as sf
from ckanext.issues.model import Ticket


def _build_support_tickets_stmt() -> sql.Select:
    """Build the stmt for the support tickets table.

    We join the CKAN User table twice (author + assignee) and expose
    COALESCE(fullname, name) as ``author_name`` / ``assignee_name`` so
    that column header filters operate on human-readable names rather
    than raw UUIDs.  The login names are included as hidden columns so
    that formatters can build profile links without a per-row lookup.

    Datetime columns are pre-formatted as ISO-style strings
    (``YYYY-MM-DD HH24:MI``) so they sort correctly as plain strings
    and can be filtered without a custom formatter.
    """
    author_alias = aliased(ckan_model.User, name="author")
    assignee_alias = aliased(ckan_model.User, name="assignee")

    author_display = func.coalesce(author_alias.fullname, author_alias.name).label("author_name")
    assignee_display = func.coalesce(assignee_alias.fullname, assignee_alias.name).label("assignee_name")

    return (
        select(
            Ticket.id,
            Ticket.subject,
            Ticket.status,
            Ticket.category,
            func.to_char(Ticket.created_at, "YYYY-MM-DD HH24:MI").label("created_at"),
            func.to_char(Ticket.updated_at, "YYYY-MM-DD HH24:MI").label("updated_at"),
            author_display,
            assignee_display,
            author_alias.name.label("author_login"),
            assignee_alias.name.label("assignee_login"),
        )
        .outerjoin(author_alias, Ticket.author_id == author_alias.id)
        .outerjoin(assignee_alias, Ticket.assignee_id == assignee_alias.id)
        .order_by(Ticket.updated_at.desc())
    )


class SupportTable(t.TableDefinition):
    def __init__(self) -> None:
        super().__init__(
            name="issues_tickets",
            table_template="issues/list.html",
            data_source=t.DatabaseDataSource(stmt=_build_support_tickets_stmt()),
            columns=[
                t.ColumnDefinition(field="subject", title=tk._("Subject")),
                t.ColumnDefinition(
                    field="status",
                    title=tk._("Status"),
                    formatters=[(sf.StatusFormatter, {})],
                    tabulator_formatter="html",
                ),
                t.ColumnDefinition(
                    field="author_name",
                    title=tk._("Author"),
                    formatters=[(sf.UserNameLinkFormatter, {"name_field": "author_login"})],
                    tabulator_formatter="html",
                ),
                t.ColumnDefinition(
                    field="assignee_name",
                    title=tk._("Assignee"),
                    formatters=[(sf.UserNameLinkFormatter, {"name_field": "assignee_login"})],
                    tabulator_formatter="html",
                ),
                t.ColumnDefinition(field="category", title=tk._("Category")),
                t.ColumnDefinition(field="created_at", title=tk._("Created At")),
                t.ColumnDefinition(field="updated_at", title=tk._("Updated At")),
            ],
            row_actions=[
                t.RowActionDefinition(
                    action="view",
                    label=tk._("View"),
                    icon="fa fa-eye",
                    callback=lambda row: t.ActionHandlerResult(
                        success=True,
                        redirect=tk.url_for("issues.ticket_read", ticket_id=row["id"]),
                    ),
                ),
                t.RowActionDefinition(
                    action="delete",
                    label=tk._("Delete"),
                    icon="fa fa-trash",
                    callback=self.row_action_delete,
                    with_confirmation=True,
                ),
            ],
            bulk_actions=[
                t.BulkActionDefinition(
                    action="close_tickets",
                    label=tk._("Close selected tickets"),
                    icon="fa fa-check",
                    callback=self.bulk_close,
                ),
                t.BulkActionDefinition(
                    action="reopen_tickets",
                    label=tk._("Reopen selected tickets"),
                    icon="fa fa-folder-open",
                    callback=self.bulk_reopen,
                ),
                t.BulkActionDefinition(
                    action="remove_tickets",
                    label=tk._("Remove selected tickets"),
                    icon="fa fa-trash",
                    callback=self.bulk_remove,
                ),
            ],
        )

    def row_action_delete(self, row: t.Row) -> t.ActionHandlerResult:
        try:
            tk.get_action("issues_ticket_delete")({"ignore_auth": True}, {"id": row["id"]})
        except (tk.ValidationError, tk.ObjectNotFound):
            return t.ActionHandlerResult(success=False, error=tk._("Error deleting ticket."))

        return t.ActionHandlerResult(success=True)

    def bulk_close(self, rows: list[t.Row]) -> t.ActionHandlerResult:
        return _apply_to_rows(
            rows,
            "issues_ticket_update",
            {"status": Ticket.Status.closed},
            tk._("Ticket(s) closed."),
        )

    def bulk_reopen(self, rows: list[t.Row]) -> t.ActionHandlerResult:
        return _apply_to_rows(
            rows,
            "issues_ticket_update",
            {"status": Ticket.Status.opened},
            tk._("Ticket(s) reopened."),
        )

    def bulk_remove(self, rows: list[t.Row]) -> t.ActionHandlerResult:
        return _apply_to_rows(rows, "issues_ticket_delete", {}, tk._("Ticket(s) removed."))


def _apply_to_rows(
    rows: list[t.Row],
    action: str,
    extra: dict[str, str],
    success_message: str,
) -> t.ActionHandlerResult:
    """Run ``action`` for every selected ticket, skipping ones that are gone.

    Each call commits on its own, so tickets processed before a failure stay
    processed; the failed ids are reported back instead of raising a 500.
    """
    failed = []
    for row in rows:
        try:
            tk.get_action(action)({"ignore_auth": True}, {"id": row["id"], **extra})
        except (tk.ValidationError, tk.ObjectNotFound):  # noqa: PERF203 - per-row errors are the point
            failed.append(str(row["id"]))

    if failed:
        return t.ActionHandlerResult(
            success=False,
            error=tk._("Some tickets could not be processed: {ids}").format(ids=", ".join(failed)),
        )

    return t.ActionHandlerResult(success=True, message=success_message)


class UserTicketTable(t.TableDefinition):
    """Table for displaying tickets created by the current user."""

    def __init__(self) -> None:
        # Access (authenticated users only) is enforced by check_access below
        # and the blueprint's before_request; an anonymous user matches no rows.
        user_id = tk.current_user.id if tk.current_user.is_authenticated else None

        stmt = (
            select(
                Ticket.id,
                Ticket.subject,
                Ticket.status,
                Ticket.category,
                func.to_char(Ticket.created_at, "YYYY-MM-DD HH24:MI").label("created_at"),
                func.to_char(Ticket.updated_at, "YYYY-MM-DD HH24:MI").label("updated_at"),
            )
            .where(Ticket.author_id == user_id)
            .order_by(Ticket.updated_at.desc())
        )

        super().__init__(
            name="my_issues_tickets",
            table_template="issues/my_tickets.html",
            data_source=t.DatabaseDataSource(stmt=stmt),
            columns=[
                t.ColumnDefinition(field="subject", title=tk._("Subject")),
                t.ColumnDefinition(
                    field="status",
                    title=tk._("Status"),
                    formatters=[(sf.StatusFormatter, {})],
                    tabulator_formatter="html",
                ),
                t.ColumnDefinition(field="category", title=tk._("Category")),
                t.ColumnDefinition(field="created_at", title=tk._("Created At")),
                t.ColumnDefinition(field="updated_at", title=tk._("Updated At")),
            ],
            row_actions=[
                t.RowActionDefinition(
                    action="view",
                    label=tk._("View"),
                    icon="fa fa-eye",
                    callback=lambda row: t.ActionHandlerResult(
                        success=True,
                        redirect=tk.url_for("issues.ticket_read", ticket_id=row["id"]),
                    ),
                ),
            ],
        )

    @classmethod
    def check_access(cls, context: types.Context) -> None:  # noqa: ARG003
        if tk.current_user.is_authenticated:
            return
        msg = tk._("You are not authorized to view this table")
        raise tk.NotAuthorized(msg)
