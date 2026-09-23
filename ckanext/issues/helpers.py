from __future__ import annotations

from typing import Any

from ckanext.issues import config as issues_config
from ckanext.issues.model import get_active_sysadmins


def issues_get_category_options() -> list[dict[str, Any]]:
    return [{"value": category, "text": category} for category in issues_config.get_ticket_categories()]


def issues_get_sysadmins() -> list[dict[str, str]]:
    return [{"value": u.id, "text": u.fullname or u.name} for u in get_active_sysadmins()]
