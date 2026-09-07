from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ckan import model

from ckanext.issues import config as issues_config


def issues_get_category_options() -> list[dict[str, Any]]:
    return [{"value": category, "text": category} for category in issues_config.get_ticket_categories()]


def issues_get_sysadmins() -> list[dict[str, str]]:
    stmt = (
        select(model.User)
        .where(model.User.sysadmin.is_(True), model.User.state == model.State.ACTIVE)
        .order_by(model.User.name)
    )
    users = model.Session.scalars(stmt).all()

    return [{"value": u.id, "text": u.fullname or u.name} for u in users]
