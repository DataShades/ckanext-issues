from __future__ import annotations

from ckan import model, types
from ckan.plugins import toolkit as tk

from ckanext.issues.model import Ticket, TicketMessage


def issues_ticket_delete(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return _sysadmin_only()


def issues_ticket_update(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return _sysadmin_only()


def issues_ticket_show(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    user = context.get("user")
    if not user:
        return {"success": False}

    if tk.h.check_access("sysadmin"):
        return {"success": True}

    ticket_id = data_dict.get("id")

    user_obj = user if isinstance(user, model.User) else model.User.get(user)
    if not user_obj:
        return {"success": False}

    ticket = Ticket.get(ticket_id)
    if ticket and ticket.author_id == user_obj.id:
        return {"success": True}

    return {"success": False}


def issues_ticket_create(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return {"success": True}


def issues_ticket_assign(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return _sysadmin_only()


def issues_message_delete(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    """Allow sysadmins to delete any message, regular users can only delete their own."""
    user = context.get("user")

    if not user:
        return {"success": False}

    if tk.h.check_access("sysadmin"):
        return {"success": True}

    message_id = data_dict.get("id")

    user_obj = user if isinstance(user, model.User) else model.User.get(user)
    if not user_obj:
        return {"success": False}

    message = TicketMessage.get(message_id)
    if message and message.author_id == user_obj.id:
        return {"success": True}

    return {"success": False}


def issues_message_update(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    """Allow sysadmins to update any message, regular users can only update their own."""
    user = context.get("user")

    if not user:
        return {"success": False}

    # Sysadmins can update any message
    if tk.h.check_access("sysadmin"):
        return {"success": True}

    # Regular users can only update their own messages
    message_id = data_dict.get("id")

    user_obj = user if isinstance(user, model.User) else model.User.get(user)
    if not user_obj:
        return {"success": False}

    message = TicketMessage.get(message_id)
    if message and message.author_id == user_obj.id:
        return {"success": True}

    return {"success": False}


def _sysadmin_only() -> types.AuthResult:
    return {"success": False}
