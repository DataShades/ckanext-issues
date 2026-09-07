from __future__ import annotations

import logging
from typing import cast

from ckan import model, types
from ckan.logic import validate
from ckan.plugins import toolkit as tk

import ckanext.issues.model as issues_model
from ckanext.issues import signals as issues_signals
from ckanext.issues.logic import schema
from ckanext.issues.types import DictizedMessage, DictizedTicket, TicketData

log = logging.getLogger(__name__)

_UPDATABLE_TICKET_FIELDS = {"status", "text"}


@validate(schema.ticket_create)
def issues_ticket_create(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_create", context, data_dict)

    ticket = issues_model.Ticket.add(TicketData(**data_dict))

    log.info("[id:%s] the ticket has been submitted", ticket["id"])

    issues_signals.ticket_created.send(ticket=ticket)

    return ticket


@tk.side_effect_free
@validate(schema.ticket_show)
def issues_ticket_show(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_show", context, data_dict)

    ticket = cast(issues_model.Ticket, issues_model.Ticket.get(data_dict["id"]))
    # Session has expire_on_commit=False, so a ticket that is already in the
    # identity map can carry a stale `messages` collection. Reload it.
    model.Session.expire(ticket)

    return ticket.dictize(context)


@tk.side_effect_free
@validate(schema.ticket_delete)
def issues_ticket_delete(context: types.Context, data_dict: types.DataDict) -> bool:
    tk.check_access("issues_ticket_delete", context, data_dict)

    ticket = cast(issues_model.Ticket, issues_model.Ticket.get(data_dict["id"]))
    ticket.delete()

    model.Session.commit()

    return True


@validate(schema.ticket_update)
def issues_ticket_update(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_update", context, data_dict)

    ticket = cast(issues_model.Ticket, issues_model.Ticket.get(data_dict["id"]))

    for key, value in data_dict.items():
        if key in _UPDATABLE_TICKET_FIELDS:
            setattr(ticket, key, value)

    ticket.updated_at = issues_model.datetime.utcnow()
    model.Session.commit()

    log.info("[id:%s] ticket been updated: %s", ticket.id, data_dict)

    dictized = ticket.dictize(context)
    issues_signals.ticket_updated.send(ticket=dictized)

    return dictized


@validate(schema.ticket_assign)
def issues_ticket_assign(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_assign", context, data_dict)

    ticket = cast(issues_model.Ticket, issues_model.Ticket.get(data_dict["id"]))

    ticket.assignee_id = data_dict.get("assignee_id")

    model.Session.commit()

    log.info("[id:%s] ticket assigned to: %s", ticket.id, ticket.assignee_id)

    dictized = ticket.dictize(context)
    issues_signals.ticket_updated.send(ticket=dictized)

    return dictized


@validate(schema.message_create)
def issues_message_create(context: types.Context, data_dict: types.DataDict) -> DictizedMessage:
    tk.check_access("issues_message_create", context, data_dict)

    ticket = cast(issues_model.Ticket, issues_model.Ticket.get(data_dict["ticket_id"]))

    if ticket.status != issues_model.Ticket.Status.opened:
        raise tk.ValidationError({"ticket_id": ["Cannot add messages to closed tickets"]})

    message = issues_model.TicketMessage.add(
        ticket_id=data_dict["ticket_id"],
        author_id=data_dict["author_id"],
        content=data_dict["content"],
    )

    # Update ticket updated_at
    ticket.updated_at = issues_model.datetime.utcnow()
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

    message = issues_model.TicketMessage.get(data_dict["id"])

    if not message:
        raise tk.ObjectNotFound("Message not found")

    message.delete()
    model.Session.commit()

    log.info("[message_id:%s] message deleted", data_dict["id"])

    return True


@validate(schema.message_update)
def issues_message_update(context: types.Context, data_dict: types.DataDict) -> DictizedMessage:
    tk.check_access("issues_message_update", context, data_dict)

    message = issues_model.TicketMessage.get(data_dict["id"])

    if not message:
        raise tk.ObjectNotFound("Message not found")

    message.update(data_dict["content"])
    model.Session.commit()

    log.info("[message_id:%s] message updated", data_dict["id"])

    return message.dictize(context)
