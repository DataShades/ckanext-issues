from __future__ import annotations

import ckan.plugins.toolkit as tk

CONF_TICKET_CATEGORIES = "ckanext.issues.category_list"
DEF_TICKET_CATEGORIES = ["Feature request", "Data request", "Bug report", "Other"]

CONF_NOTIFY_NEW_TICKET = "ckanext.issues.notify_on_new_ticket"
CONF_NOTIFY_NEW_MESSAGE = "ckanext.issues.notify_on_new_message"
CONF_NOTIFY_TICKET_UPDATE = "ckanext.issues.notify_on_ticket_update"
CONF_NOTIFY_TICKET_ASSIGN = "ckanext.issues.notify_on_ticket_assign"

CONF_MAIL_QUEUE = "ckanext.issues.mail_queue"
DEF_MAIL_QUEUE = "default"

CONF_MAX_OPEN_TICKETS = "ckanext.issues.max_open_tickets_per_user"
DEF_MAX_OPEN_TICKETS = 5

CONF_ATTACHMENTS_STORAGE = "ckanext.issues.attachments.storage"
CONF_ATTACHMENTS_MAX_FILES = "ckanext.issues.attachments.max_files"
DEF_ATTACHMENTS_MAX_FILES = 5
CONF_ATTACHMENTS_MAX_SIZE = "ckanext.issues.attachments.max_size"
DEF_ATTACHMENTS_MAX_SIZE = 10 * 1024 * 1024
CONF_ATTACHMENTS_ALLOWED_TYPES = "ckanext.issues.attachments.allowed_types"
DEF_ATTACHMENTS_ALLOWED_TYPES = [
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/json",
    "application/zip",
]


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


def get_notify_on_ticket_assign() -> bool:
    return tk.asbool(tk.config.get(CONF_NOTIFY_TICKET_ASSIGN, True))


def get_mail_queue() -> str:
    """Background-job queue that notification mails are enqueued on."""
    return tk.config.get(CONF_MAIL_QUEUE) or DEF_MAIL_QUEUE


def get_attachments_storage() -> str:
    """Name of the ckanext-files storage attachments are written to.

    Empty means the default storage of ckanext-files (or CKAN core on 2.12+).
    """
    return tk.config.get(CONF_ATTACHMENTS_STORAGE) or ""


def get_attachments_max_files() -> int:
    """How many files one ticket or reply may carry. ``0`` disables uploads."""
    return tk.asint(tk.config.get(CONF_ATTACHMENTS_MAX_FILES, DEF_ATTACHMENTS_MAX_FILES))


def get_attachments_max_size() -> int:
    """Largest accepted file, in bytes. ``0`` means no limit."""
    return tk.asint(tk.config.get(CONF_ATTACHMENTS_MAX_SIZE, DEF_ATTACHMENTS_MAX_SIZE))


def get_attachments_allowed_types() -> list[str]:
    """Accepted MIME types; ``type/*`` matches a whole family, empty allows any.

    Matched against the type detected from the file content, not the one the
    browser reports.
    """
    raw = tk.config.get(CONF_ATTACHMENTS_ALLOWED_TYPES)
    if raw is None:
        return list(DEF_ATTACHMENTS_ALLOWED_TYPES)

    values = raw if isinstance(raw, (list, tuple)) else str(raw).split()
    return [str(value).strip().lower() for value in values if str(value).strip()]
