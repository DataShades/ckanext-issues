from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk
from ckan import model, types

import ckanext.issues.config as issues_config
from ckanext.issues.model import Ticket, TicketMessage


def ticket_id_exists(ticket_id: str, context: types.Context) -> Any:
    """Ensures that the ticket with a given id exists."""
    if not Ticket.get(ticket_id):
        msg = tk._("Ticket not found")
        raise tk.Invalid(msg)

    return ticket_id


def message_id_exists(message_id: str, context: types.Context) -> Any:
    """Ensures that the message with a given id exists."""
    if not TicketMessage.get(message_id):
        msg = tk._("Message not found")
        raise tk.Invalid(msg)

    return message_id


def issues_category_validator(ticket_category: str) -> str:
    allowed_categories = issues_config.get_ticket_categories()

    if ticket_category not in allowed_categories:
        msg = tk._("Category {category} is not allowed").format(category=ticket_category)
        raise tk.Invalid(msg)

    return ticket_category


def issues_assignee_validator(user_id_or_name: str, context: types.Context) -> Any:
    """Ensure the assignee is an active sysadmin; normalise it to the user id."""
    user = model.User.get(user_id_or_name)
    if not user or user.state != model.State.ACTIVE or not user.sysadmin:
        msg = tk._("Tickets can only be assigned to an active sysadmin")
        raise tk.Invalid(msg)

    return user.id
