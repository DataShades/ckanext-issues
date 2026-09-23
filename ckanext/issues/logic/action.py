from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from ckan import model, types
from ckan.logic import validate
from ckan.plugins import toolkit as tk

import ckanext.issues.model as issues_model
from ckanext.issues import config
from ckanext.issues import signals as issues_signals
from ckanext.issues.logic import schema
from ckanext.issues.types import DictizedMessage, DictizedTicket, TicketData

log = logging.getLogger(__name__)

_UPDATABLE_TICKET_FIELDS = {"status"}


def _get_ticket(ticket_id: Any) -> issues_model.Ticket:
    """Fetch a ticket or raise ObjectNotFound.

    Schema validation already checked the id exists, but the row can be gone
    by the time we fetch it (a concurrent delete), and ``ticket_show`` /
    ``ticket_delete`` allow a missing id.
    """
    ticket = issues_model.Ticket.get(ticket_id)
    if ticket is None:
        msg = tk._("Ticket not found")
        raise tk.ObjectNotFound(msg)
    return ticket


def _get_message(message_id: Any) -> issues_model.TicketMessage:
    """Fetch a message or raise ObjectNotFound."""
    message = issues_model.TicketMessage.get(message_id)
    if message is None:
        msg = tk._("Message not found")
        raise tk.ObjectNotFound(msg)
    return message


def _enforce_open_ticket_limit(context: types.Context, author_id: str) -> None:
    """Reject creation when the author already has too many open tickets.

    Sysadmins and internal (``ignore_auth``) callers are exempt; a limit of
    ``0`` disables the check.
    """
    if context.get("ignore_auth"):
        return

    limit = config.get_max_open_tickets_per_user()
    if limit <= 0:
        return

    user = model.User.get(author_id)
    if not user or user.sysadmin:
        return

    # Lock the author's row until the ticket is committed, so concurrent
    # submissions are serialised and can't all pass the count below.
    model.Session.execute(sa.select(model.User.id).where(model.User.id == user.id).with_for_update())

    if issues_model.Ticket.count_open_for_author(user.id) >= limit:
        raise tk.ValidationError(
            {
                "author_id": [
                    tk._(
                        "You already have {n} open support tickets. Please wait "
                        "for one to be resolved before opening another."
                    ).format(n=limit)
                ]
            }
        )


@validate(schema.ticket_create)
def issues_ticket_create(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_create", context, data_dict)
    _enforce_open_ticket_limit(context, data_dict["author_id"])

    ticket = issues_model.Ticket.add(TicketData(**data_dict))
    model.Session.commit()

    log.info("[id:%s] the ticket has been submitted", ticket.id)

    dictized = ticket.dictize(context)
    issues_signals.ticket_created.send(ticket=dictized)

    return dictized


@tk.side_effect_free
@validate(schema.ticket_show)
def issues_ticket_show(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_show", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))

    return ticket.dictize(context)


@validate(schema.ticket_delete)
def issues_ticket_delete(context: types.Context, data_dict: types.DataDict) -> bool:
    tk.check_access("issues_ticket_delete", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))
    dictized = ticket.dictize(context)
    ticket.delete()

    model.Session.commit()

    log.info("[id:%s] ticket deleted", dictized["id"])

    issues_signals.ticket_deleted.send(ticket=dictized)

    return True


@validate(schema.ticket_update)
def issues_ticket_update(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_update", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))

    changes = {
        key: value
        for key, value in data_dict.items()
        if key in _UPDATABLE_TICKET_FIELDS and getattr(ticket, key) != value
    }
    if not changes:
        # e.g. bulk-closing an already closed ticket: no write, no notification
        return ticket.dictize(context)

    for key, value in changes.items():
        setattr(ticket, key, value)

    model.Session.commit()

    log.info("[id:%s] ticket updated, status: %s", ticket.id, ticket.status)

    dictized = ticket.dictize(context)
    issues_signals.ticket_updated.send(ticket=dictized)

    return dictized


@validate(schema.ticket_assign)
def issues_ticket_assign(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_assign", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))

    assignee_id = data_dict.get("assignee_id")
    if ticket.assignee_id == assignee_id:
        return ticket.dictize(context)

    # Set the relationship, not just the column: the session doesn't expire
    # on commit, so an already-loaded ``ticket.assignee`` would stay stale.
    ticket.assignee = model.User.get(assignee_id) if assignee_id else None

    model.Session.commit()

    log.info("[id:%s] ticket assigned to: %s", ticket.id, ticket.assignee_id)

    dictized = ticket.dictize(context)
    issues_signals.ticket_updated.send(ticket=dictized)
    if dictized["assignee"]:
        issues_signals.ticket_assigned.send(ticket=dictized)

    return dictized


@validate(schema.message_create)
def issues_message_create(context: types.Context, data_dict: types.DataDict) -> DictizedMessage:
    tk.check_access("issues_message_create", context, data_dict)

    ticket = _get_ticket(data_dict.get("ticket_id"))

    if ticket.status != issues_model.Ticket.Status.opened:
        raise tk.ValidationError({"ticket_id": [tk._("Cannot add messages to closed tickets")]})

    message = issues_model.TicketMessage.add(
        ticket,
        author_id=data_dict["author_id"],
        content=data_dict["content"],
    )
    ticket.touch()
    model.Session.commit()

    log.info(
        "[ticket_id:%s] new message from %s",
        data_dict["ticket_id"],
        data_dict["author_id"],
    )

    dictized_message = message.dictize(context)

    issues_signals.message_created.send(
        ticket=ticket.dictize(context),
        message=dictized_message,
    )

    return dictized_message


@validate(schema.message_delete)
def issues_message_delete(context: types.Context, data_dict: types.DataDict) -> bool:
    tk.check_access("issues_message_delete", context, data_dict)

    message = _get_message(data_dict.get("id"))
    message.delete()
    model.Session.commit()

    log.info("[message_id:%s] message deleted", data_dict["id"])

    return True


@validate(schema.message_update)
def issues_message_update(context: types.Context, data_dict: types.DataDict) -> DictizedMessage:
    tk.check_access("issues_message_update", context, data_dict)

    message = _get_message(data_dict.get("id"))
    message.update(data_dict["content"])
    model.Session.commit()

    log.info("[message_id:%s] message updated", data_dict["id"])

    return message.dictize(context)
