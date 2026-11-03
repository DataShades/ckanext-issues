from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from ckan import model, types
from ckan.logic import validate
from ckan.plugins import toolkit as tk

import ckanext.issues.model as issues_model
from ckanext.issues import attachments, config
from ckanext.issues import signals as issues_signals
from ckanext.issues.logic import schema
from ckanext.issues.types import DictizedMessage, DictizedTicket, TicketData

if TYPE_CHECKING:
    from collections.abc import Iterator

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


def _dictize_ticket(ticket: issues_model.Ticket, context: types.Context) -> DictizedTicket:
    """Dictize a ticket with the files attached to it and to its messages."""
    dictized = ticket.dictize(context)

    files = attachments.list_for(attachments.OWNER_TICKET, [ticket.id])
    dictized["attachments"] = files.get(str(ticket.id), [])

    by_message = attachments.list_for(attachments.OWNER_MESSAGE, [m["id"] for m in dictized["messages"]])
    for message in dictized["messages"]:
        message["attachments"] = by_message.get(str(message["id"]), [])

    return dictized


def _dictize_message(message: issues_model.TicketMessage, context: types.Context) -> DictizedMessage:
    dictized = message.dictize(context)
    files = attachments.list_for(attachments.OWNER_MESSAGE, [message.id])
    dictized["attachments"] = files.get(str(message.id), [])
    return dictized


def _message_file_ids(ticket: issues_model.Ticket) -> list[str]:
    return attachments.file_ids_for(attachments.OWNER_MESSAGE, [m.id for m in ticket.messages])


def _attachment_error(err: Exception) -> tk.ValidationError:
    message = tk._("The files could not be saved. Please try again.")
    if isinstance(err, tk.ValidationError):
        message = "; ".join(str(m) for m in err.error_summary.values()) or message
    return tk.ValidationError({attachments.FIELD: [message]})


def _store_uploads(uploads: list[Any], user: str) -> list[str]:
    """Store uploads before their ticket or message exists (see attachments.store)."""
    if not uploads:
        return []

    try:
        return attachments.store(uploads, user)
    except Exception as err:
        raise _attachment_error(err) from err


def _assign_or_undo(
    owner: issues_model.Ticket | issues_model.TicketMessage, file_ids: list[str], user: str
) -> None:
    """Give stored files to a just-committed ticket or message.

    If that fails, the owner and the files are deleted again so the user can
    resubmit, and the failure is reported on ``attachments``.
    """
    if not file_ids:
        return

    owner_type = attachments.OWNER_TICKET if isinstance(owner, issues_model.Ticket) else attachments.OWNER_MESSAGE

    try:
        attachments.assign(owner_type, owner.id, file_ids, user)
    except Exception as err:
        log.exception("[%s:%s] could not attach files", owner_type, owner.id)
        model.Session.rollback()
        owner.delete()
        model.Session.commit()
        attachments.delete_files(file_ids)
        raise _attachment_error(err) from err


@contextlib.contextmanager
def _discard_on_error(file_ids: list[str]) -> Iterator[None]:
    """Delete stored files if creating their ticket or message fails."""
    try:
        yield
    except Exception:
        if file_ids:
            model.Session.rollback()
            attachments.delete_files(file_ids)
        raise


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

    uploads = data_dict.pop(attachments.FIELD, [])
    user = context.get("user") or data_dict["author_id"]

    # Store files first: storing commits, which would release the row lock
    # taken by the open-ticket limit check.
    file_ids = _store_uploads(uploads, user)

    with _discard_on_error(file_ids):
        _enforce_open_ticket_limit(context, data_dict["author_id"])
        ticket = issues_model.Ticket.add(TicketData(**data_dict))
        model.Session.commit()

    _assign_or_undo(ticket, file_ids, user)

    log.info("[id:%s] the ticket has been submitted", ticket.id)

    dictized = _dictize_ticket(ticket, context)
    issues_signals.ticket_created.send(ticket=dictized)

    return dictized


@tk.side_effect_free
@validate(schema.ticket_show)
def issues_ticket_show(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_show", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))

    return _dictize_ticket(ticket, context)


@validate(schema.ticket_delete)
def issues_ticket_delete(context: types.Context, data_dict: types.DataDict) -> bool:
    tk.check_access("issues_ticket_delete", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))
    dictized = _dictize_ticket(ticket, context)
    file_ids = [f["id"] for f in dictized.get("attachments", [])] + _message_file_ids(ticket)
    ticket.delete()

    model.Session.commit()

    # After the commit: a file that fails to go is only an orphan, while
    # deleting files first could leave a ticket pointing at missing ones.
    attachments.delete_files(file_ids)

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
        return _dictize_ticket(ticket, context)

    for key, value in changes.items():
        setattr(ticket, key, value)

    model.Session.commit()

    log.info("[id:%s] ticket updated, status: %s", ticket.id, ticket.status)

    dictized = _dictize_ticket(ticket, context)
    issues_signals.ticket_updated.send(ticket=dictized)

    return dictized


@validate(schema.ticket_assign)
def issues_ticket_assign(context: types.Context, data_dict: types.DataDict) -> DictizedTicket:
    tk.check_access("issues_ticket_assign", context, data_dict)

    ticket = _get_ticket(data_dict.get("id"))

    assignee_id = data_dict.get("assignee_id")
    if ticket.assignee_id == assignee_id:
        return _dictize_ticket(ticket, context)

    # Set the relationship, not just the column: the session doesn't expire
    # on commit, so an already-loaded ``ticket.assignee`` would stay stale.
    ticket.assignee = model.User.get(assignee_id) if assignee_id else None

    model.Session.commit()

    log.info("[id:%s] ticket assigned to: %s", ticket.id, ticket.assignee_id)

    dictized = _dictize_ticket(ticket, context)
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

    user = context.get("user") or data_dict["author_id"]
    file_ids = _store_uploads(data_dict.get(attachments.FIELD, []), user)

    with _discard_on_error(file_ids):
        message = issues_model.TicketMessage.add(
            ticket,
            author_id=data_dict["author_id"],
            content=data_dict["content"],
        )
        ticket.touch()
        model.Session.commit()

    _assign_or_undo(message, file_ids, user)

    log.info(
        "[ticket_id:%s] new message from %s",
        data_dict["ticket_id"],
        data_dict["author_id"],
    )

    dictized_message = _dictize_message(message, context)

    issues_signals.message_created.send(
        ticket=_dictize_ticket(ticket, context),
        message=dictized_message,
    )

    return dictized_message


@validate(schema.message_delete)
def issues_message_delete(context: types.Context, data_dict: types.DataDict) -> bool:
    tk.check_access("issues_message_delete", context, data_dict)

    message = _get_message(data_dict.get("id"))
    file_ids = attachments.file_ids_for(attachments.OWNER_MESSAGE, [message.id])
    message.delete()
    model.Session.commit()

    attachments.delete_files(file_ids)

    log.info("[message_id:%s] message deleted", data_dict["id"])

    return True


@validate(schema.message_update)
def issues_message_update(context: types.Context, data_dict: types.DataDict) -> DictizedMessage:
    tk.check_access("issues_message_update", context, data_dict)

    message = _get_message(data_dict.get("id"))
    message.update(data_dict["content"])
    model.Session.commit()

    log.info("[message_id:%s] message updated", data_dict["id"])

    return _dictize_message(message, context)
