from __future__ import annotations

from ckan import model, types

from ckanext.issues.model import Ticket, TicketMessage

# NOTE: ckan.authz grants sysadmins access before these functions are called,
# so none of them need an explicit sysadmin branch.


def issues_ticket_delete(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return _sysadmin_only()


def issues_ticket_update(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return _sysadmin_only()


def issues_ticket_show(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    user = context.get("user")
    if not user:
        return {"success": False}

    user_obj = user if isinstance(user, model.User) else model.User.get(user)
    if not user_obj:
        return {"success": False}

    ticket = Ticket.get(data_dict.get("id", ""))

    if ticket and ticket.author_id == user_obj.id:
        return {"success": True}

    return {"success": False}


def issues_ticket_create(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return {"success": True}


def issues_ticket_assign(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    return _sysadmin_only()


def issues_message_delete(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    """Regular users can only delete their own messages."""
    return _own_message_only(context, data_dict)


def issues_message_update(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    """Regular users can only update their own messages."""
    return _own_message_only(context, data_dict)


def _own_message_only(context: types.Context, data_dict: types.DataDict) -> types.AuthResult:
    user = context.get("user")
    if not user:
        return {"success": False}

    user_obj = user if isinstance(user, model.User) else model.User.get(user)
    if not user_obj:
        return {"success": False}

    message = TicketMessage.get(data_dict.get("id"))
    if message and message.author_id == user_obj.id:
        return {"success": True}

    return {"success": False}


def _sysadmin_only() -> types.AuthResult:
    return {"success": False}
