from __future__ import annotations

from markupsafe import escape

import ckan.plugins.toolkit as tk

from ckanext.tables.shared import FormatterResult, Options, Value, formatters

from ckanext.issues.model import Ticket

_STATUS_BADGE_CLASSES = {
    Ticket.Status.opened: "bg-success",
    Ticket.Status.closed: "bg-secondary",
}


class StatusFormatter(formatters.BaseFormatter):
    """Render the ticket status as a coloured badge."""

    def format(self, value: Value, options: Options) -> FormatterResult:  # noqa: ARG002
        badge_class = _STATUS_BADGE_CLASSES.get(str(value))
        if not badge_class:
            return ""

        label = tk.h.issues_status_label(value)
        return tk.literal(f'<span class="badge {badge_class} text-white">{escape(label)}</span>')


class TicketLinkFormatter(formatters.BaseFormatter):
    """Render the ticket subject as a link to the ticket page."""

    def format(self, value: Value, options: Options) -> FormatterResult:  # noqa: ARG002
        url = tk.h.url_for("issues.ticket_read", ticket_id=self.initial_row["id"])
        return tk.literal(f'<a href="{escape(url)}">{escape(value)}</a>')


class UserNameLinkFormatter(formatters.BaseFormatter):
    """Render an avatar + profile link for a user.

    The ``value`` here is already the human-readable display name (resolved by
    the SQL query via ``COALESCE(fullname, name)``), so the column can be
    made filterable without confusing users with UUID searches.

    The profile URL is built from the user's login name, which the query
    selects into the row as well, so no per-row user lookup is needed.

    Options:
        - ``name_field`` (str) - Row key that holds the user's login name.
          **Required.**
        - ``maxlength`` (int) - Clip display name to this length. Default 20.
        - ``avatar`` (int) - Avatar placeholder size in pixels. Default 20.
    """

    def format(self, value: Value, options: Options) -> FormatterResult:
        if not value:
            return ""

        name_field = options.get("name_field")
        user_name = self.initial_row.get(name_field) if name_field else None

        maxlength: int = options.get("maxlength") or 20
        avatar: int = options.get("avatar") or 20

        display_name = str(value)
        if len(display_name) > maxlength:
            display_name = display_name[:maxlength] + "..."

        icon = (
            f'<img class="user-image" width="{avatar}" height="{avatar}" '
            f'src="{escape(tk.h.url_for_static("/base/images/placeholder-user.png"))}" '
            f'alt="{escape(display_name)}" />'
        )
        link = (
            tk.h.link_to(display_name, tk.h.url_for("user.read", id=user_name)) if user_name else escape(display_name)
        )

        return tk.literal(f"{icon} {link}")
