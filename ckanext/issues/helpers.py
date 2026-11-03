from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.issues import attachments
from ckanext.issues import config as issues_config
from ckanext.issues.model import Ticket, get_active_sysadmins
from ckanext.issues.table import SUPPORT_TABS, SupportScope, support_scope_counts


def issues_get_category_options() -> list[dict[str, Any]]:
    return [{"value": category, "text": category} for category in issues_config.get_ticket_categories()]


def issues_status_label(status: str) -> str:
    """Human-readable, translated label for a ticket status value."""
    return tk._("Open") if status == Ticket.Status.opened else tk._("Closed")


def issues_get_sysadmins() -> list[dict[str, str]]:
    return [{"value": u.id, "text": u.fullname or u.name} for u in get_active_sysadmins()]


def issues_support_tabs() -> list[dict[str, Any]]:
    """The support queue tabs, with ticket counts and the current one marked."""
    labels = {
        SupportScope.open: tk._("Open"),
        SupportScope.needs_reply: tk._("Needs reply"),
        SupportScope.unassigned: tk._("Unassigned"),
        SupportScope.mine: tk._("Assigned to me"),
        SupportScope.closed: tk._("Closed"),
        SupportScope.all: tk._("All"),
    }
    counts = support_scope_counts()
    current = tk.request.endpoint

    return [
        {
            "label": labels[tab.scope],
            "url": tk.h.url_for(f"issues_admin.{tab.endpoint}"),
            "count": counts[tab.scope],
            "active": current == f"issues_admin.{tab.endpoint}",
        }
        for tab in SUPPORT_TABS
    ]


def issues_attachments_enabled() -> bool:
    """Whether the upload controls should be shown."""
    return attachments.uploads_allowed()


def issues_attachment_url(file_id: str) -> str:
    """Download link of an attachment; access is checked by ckanext-files."""
    return tk.h.url_for("files.dispatch_download", file_id=file_id)


def issues_attachment_accept() -> str:
    """Value for the file input's ``accept`` attribute (a hint, not a check)."""
    return ",".join(issues_config.get_attachments_allowed_types())


def issues_attachment_limits() -> dict[str, Any]:
    return {
        "max_files": issues_config.get_attachments_max_files(),
        "max_size": issues_config.get_attachments_max_size(),
    }


def issues_attachment_is_image(content_type: str | None) -> bool:
    return bool(content_type) and content_type.lower().startswith("image/")
