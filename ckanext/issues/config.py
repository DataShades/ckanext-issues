from __future__ import annotations

import ckan.plugins.toolkit as tk

CONF_TICKET_CATEGORIES = "ckanext.issues.category_list"
DEF_TICKET_CATEGORIES = ["Feature request", "Data request", "Bug report", "Other"]

CONF_NOTIFY_NEW_TICKET = "ckanext.issues.notify_on_new_ticket"
CONF_NOTIFY_NEW_MESSAGE = "ckanext.issues.notify_on_new_message"
CONF_NOTIFY_TICKET_UPDATE = "ckanext.issues.notify_on_ticket_update"

CONF_MAX_OPEN_TICKETS = "ckanext.issues.max_open_tickets_per_user"
DEF_MAX_OPEN_TICKETS = 5


def get_ticket_categories() -> list[str]:
    """Return the configured ticket categories, one per line.

    Category names may contain spaces, so the config value is split on
    newlines only (indent the continuation lines in the ini)::

        ckanext.issues.category_list =
            Feature request
            Bug report
    """
    raw = tk.config.get(CONF_TICKET_CATEGORIES)
    lines = raw if isinstance(raw, (list, tuple)) else str(raw or "").splitlines()

    categories = [str(line).strip() for line in lines if str(line).strip()]
    return categories or list(DEF_TICKET_CATEGORIES)


def get_max_open_tickets_per_user() -> int:
    """Cap on tickets a non-sysadmin user may keep in the ``opened`` state.

    ``0`` (or a negative value) disables the check.
    """
    return tk.asint(tk.config.get(CONF_MAX_OPEN_TICKETS, DEF_MAX_OPEN_TICKETS))


def get_notify_on_new_ticket() -> bool:
    return tk.asbool(tk.config.get(CONF_NOTIFY_NEW_TICKET, True))


def get_notify_on_new_message() -> bool:
    return tk.asbool(tk.config.get(CONF_NOTIFY_NEW_MESSAGE, True))


def get_notify_on_ticket_update() -> bool:
    return tk.asbool(tk.config.get(CONF_NOTIFY_TICKET_UPDATE, True))
