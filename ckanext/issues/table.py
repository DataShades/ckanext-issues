from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from sqlalchemy import and_, func, select, sql
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

    Datetime columns stay real timestamps so they sort chronologically; the
    formatter renders them in the display timezone, like the ticket page.
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
            Ticket.created_at,
            Ticket.updated_at,
            author_display,
            assignee_display,
            author_alias.name.label("author_login"),
            assignee_alias.name.label("assignee_login"),
        )
        .outerjoin(author_alias, Ticket.author_id == author_alias.id)
        .outerjoin(assignee_alias, Ticket.assignee_id == assignee_alias.id)
        .order_by(Ticket.updated_at.desc())
    )


def _confirm_attrs(title: str, message: str, button: str, *, destructive: bool = False) -> dict[str, str]:
    """``data-confirm-*`` attributes that ckanext-tables turns into the dialog.

    Destructive actions get core's red ``danger`` style and start on Cancel.
    """
    attrs = {
        "data-confirm-title": title,
        "data-confirm-message": message,
        "data-confirm-text": button,
    }
    if destructive:
        attrs.update({"data-confirm-type": "danger", "data-confirm-focus": "cancel"})
    return attrs


def _subject_column() -> t.ColumnDefinition:
    # The subject is what people scan for; keep it from being squeezed to a
    # few characters, and show the full text on hover when it is clipped.
    return t.ColumnDefinition(
        field="subject",
        title=tk._("Subject"),
        formatters=[(sf.TicketLinkFormatter, {})],
        tabulator_formatter="html",
        min_width=280,
        tooltip=True,
    )


def _status_column() -> t.ColumnDefinition:
    return t.ColumnDefinition(
        field="status",
        title=tk._("Status"),
        formatters=[(sf.StatusFormatter, {})],
        tabulator_formatter="html",
        width=130,
    )


def _date_columns(*, show_created: bool = True) -> list[t.ColumnDefinition]:
    formatters = [(t.formatters.DateFormatter, {"date_format": "%Y-%m-%d %H:%M"})]
    return [
        t.ColumnDefinition(field="created_at", title=tk._("Created"), formatters=formatters, visible=show_created),
        t.ColumnDefinition(field="updated_at", title=tk._("Updated"), formatters=formatters),
    ]


class SupportScope:
    """Which tickets a tab of the support queue shows."""

    open = "open"
    unassigned = "unassigned"
    mine = "mine"
    closed = "closed"
    all = "all"


def _scope_condition(scope: str) -> sql.ColumnElement[bool] | None:
    """The WHERE condition for a support queue tab; ``None`` means every ticket.

    "Unassigned" and "Assigned to me" are work lists, so they only hold open
    tickets.
    """
    is_open = Ticket.status == Ticket.Status.opened
    user_id = tk.current_user.id if tk.current_user.is_authenticated else None

    conditions: dict[str, sql.ColumnElement[bool] | None] = {
        SupportScope.open: is_open,
        SupportScope.unassigned: and_(is_open, Ticket.assignee_id.is_(None)),
        SupportScope.mine: and_(is_open, Ticket.assignee_id == user_id),
        SupportScope.closed: Ticket.status == Ticket.Status.closed,
        SupportScope.all: None,
    }
    return conditions[scope]


def support_scope_counts() -> dict[str, int]:
    """Number of tickets in every support queue tab, in one query."""
    scopes = [
        SupportScope.open,
        SupportScope.unassigned,
        SupportScope.mine,
        SupportScope.closed,
        SupportScope.all,
    ]
    counts = []
    for scope in scopes:
        condition = _scope_condition(scope)
        counts.append(func.count().filter(condition) if condition is not None else func.count())

    row = ckan_model.Session.execute(select(*counts).select_from(Ticket)).one()
    return dict(zip(scopes, row, strict=True))


class SupportTable(t.TableDefinition):
    """The support queue; the base class shows open tickets.

    Each tab is a subclass with its own ``scope`` (and its own route), so the
    table's AJAX and export requests, which only know the URL path and the
    table class, stay on the same tab.
    """

    scope: ClassVar[str] = SupportScope.open

    def __init__(self) -> None:
        stmt = _build_support_tickets_stmt()
        condition = _scope_condition(self.scope)
        if condition is not None:
            stmt = stmt.where(condition)

        super().__init__(
            name="issues_tickets",
            table_template="issues/list.html",
            data_source=t.DatabaseDataSource(stmt=stmt),
            columns=[
                _subject_column(),
                _status_column(),
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
                # Hidden by default so the subject and people columns have room;
                # it can be turned back on from the Columns menu.
                *_date_columns(show_created=False),
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
                    attrs=_confirm_attrs(
                        tk._("Delete ticket?"),
                        tk._(
                            "The ticket and its whole conversation will be permanently deleted. This cannot be undone."
                        ),
                        tk._("Delete ticket"),
                        destructive=True,
                    ),
                ),
            ],
            bulk_actions=[
                t.BulkActionDefinition(
                    action="close_tickets",
                    label=tk._("Close selected tickets"),
                    icon="fa fa-check",
                    callback=self.bulk_close,
                    attrs=_confirm_attrs(
                        tk._("Close tickets?"),
                        tk._(
                            "Authors of the selected tickets will no longer be able to reply. "
                            "You can reopen them later."
                        ),
                        tk._("Close tickets"),
                    ),
                ),
                t.BulkActionDefinition(
                    action="reopen_tickets",
                    label=tk._("Reopen selected tickets"),
                    icon="fa fa-folder-open",
                    callback=self.bulk_reopen,
                    attrs=_confirm_attrs(
                        tk._("Reopen tickets?"),
                        tk._("The selected tickets will be open for replies again."),
                        tk._("Reopen tickets"),
                    ),
                ),
                t.BulkActionDefinition(
                    action="delete_tickets",
                    label=tk._("Delete selected tickets"),
                    icon="fa fa-trash",
                    callback=self.bulk_delete,
                    with_confirmation=True,
                    attrs=_confirm_attrs(
                        tk._("Delete tickets?"),
                        tk._(
                            "The selected tickets and their conversations will be permanently deleted. "
                            "This cannot be undone."
                        ),
                        tk._("Delete tickets"),
                        destructive=True,
                    ),
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

    def bulk_delete(self, rows: list[t.Row]) -> t.ActionHandlerResult:
        return _apply_to_rows(rows, "issues_ticket_delete", {}, tk._("Ticket(s) deleted."))


class UnassignedSupportTable(SupportTable):
    scope = SupportScope.unassigned


class MySupportTable(SupportTable):
    scope = SupportScope.mine


class ClosedSupportTable(SupportTable):
    scope = SupportScope.closed


class AllSupportTable(SupportTable):
    scope = SupportScope.all


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
                Ticket.created_at,
                Ticket.updated_at,
            )
            .where(Ticket.author_id == user_id)
            .order_by(Ticket.updated_at.desc())
        )

        super().__init__(
            name="my_issues_tickets",
            table_template="issues/my_tickets.html",
            data_source=t.DatabaseDataSource(stmt=stmt),
            placeholder=tk._("You haven't created any support tickets yet."),
            columns=[
                _subject_column(),
                _status_column(),
                t.ColumnDefinition(field="category", title=tk._("Category")),
                *_date_columns(),
            ],
            # No row actions: the subject already links to the ticket.
        )

    @classmethod
    def check_access(cls, context: types.Context) -> None:  # noqa: ARG003
        if tk.current_user.is_authenticated:
            return
        msg = tk._("You are not authorized to view this table")
        raise tk.NotAuthorized(msg)


@dataclass(frozen=True)
class SupportTab:
    scope: str
    path: str
    endpoint: str  # within the issues_admin blueprint
    table: type[SupportTable]


SUPPORT_TABS = [
    SupportTab(SupportScope.open, "/", "list", SupportTable),
    SupportTab(SupportScope.unassigned, "/unassigned", "list_unassigned", UnassignedSupportTable),
    SupportTab(SupportScope.mine, "/mine", "list_mine", MySupportTable),
    SupportTab(SupportScope.closed, "/closed", "list_closed", ClosedSupportTable),
    SupportTab(SupportScope.all, "/all", "list_all", AllSupportTable),
]
