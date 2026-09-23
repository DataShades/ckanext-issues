"""Email notifications for ticket activity.

Signal handlers only decide *whether* to notify and enqueue a background job;
the job renders and sends the mails. This keeps the action independent of a
request context (CLI / job callers) and means an SMTP failure can't turn an
already committed change into a 500.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from flask import has_request_context

import ckan.config.middleware
import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib import mailer

from ckanext.issues import config
from ckanext.issues.model import get_active_sysadmins

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from ckanext.issues.types import DictizedMessage, DictizedTicket

log = logging.getLogger(__name__)


# Signal handlers


def notify_admins_on_new_ticket(sender: None, **kwargs: Any) -> None:
    """Subscribed to ``issues:ticket_created``; kwargs: ``ticket``."""
    if not config.get_notify_on_new_ticket():
        return

    ticket: DictizedTicket = kwargs["ticket"]
    _enqueue(send_new_ticket_emails, ticket, title=f"issues: new ticket #{ticket['id']}")


def notify_author_on_new_message(sender: None, **kwargs: Any) -> None:
    """Subscribed to ``issues:message_created``; kwargs: ``ticket``, ``message``."""
    if not config.get_notify_on_new_message():
        return

    ticket: DictizedTicket = kwargs["ticket"]
    message: DictizedMessage = kwargs["message"]

    # Don't send a notification when the author is replying to themselves.
    if message["author"]["id"] == ticket["author"]["id"]:
        return

    _enqueue(send_new_message_email, ticket, message, title=f"issues: reply on ticket #{ticket['id']}")


def notify_author_on_ticket_update(sender: None, **kwargs: Any) -> None:
    """Subscribed to ``issues:ticket_updated``; kwargs: ``ticket``."""
    if not config.get_notify_on_ticket_update():
        return

    ticket: DictizedTicket = kwargs["ticket"]
    _enqueue(send_ticket_updated_email, ticket, title=f"issues: ticket #{ticket['id']} updated")


def notify_assignee_on_assign(sender: None, **kwargs: Any) -> None:
    """Subscribed to ``issues:ticket_assigned``; kwargs: ``ticket``."""
    if not config.get_notify_on_ticket_assign():
        return

    ticket: DictizedTicket = kwargs["ticket"]
    _enqueue(send_ticket_assigned_email, ticket, title=f"issues: ticket #{ticket['id']} assigned")


def send_new_ticket_emails(ticket: DictizedTicket) -> None:
    with _request_context():
        _mail_users(
            get_active_sysadmins(),
            tk._("New support ticket: {subject}").format(subject=ticket["subject"]),
            "issues/emails/new_ticket.txt",
            {"ticket": ticket},
        )


def send_new_message_email(ticket: DictizedTicket, message: DictizedMessage) -> None:
    with _request_context():
        _mail_users(
            _users(ticket["author"]["id"]),
            tk._("New reply on your ticket: {subject}").format(subject=ticket["subject"]),
            "issues/emails/new_message.txt",
            {"ticket": ticket, "message": message},
        )


def send_ticket_updated_email(ticket: DictizedTicket) -> None:
    with _request_context():
        _mail_users(
            _users(ticket["author"]["id"]),
            tk._("Ticket updated: {subject}").format(subject=ticket["subject"]),
            "issues/emails/ticket_updated.txt",
            {"ticket": ticket},
        )


def send_ticket_assigned_email(ticket: DictizedTicket) -> None:
    assignee = ticket["assignee"]
    if not assignee:
        return

    with _request_context():
        _mail_users(
            _users(assignee["id"]),
            tk._("Ticket assigned to you: {subject}").format(subject=ticket["subject"]),
            "issues/emails/ticket_assigned.txt",
            {"ticket": ticket},
        )


def _enqueue(job: Any, *args: Any, title: str) -> None:
    tk.enqueue_job(job, list(args), title=title, queue=config.get_mail_queue())


@contextlib.contextmanager
def _request_context() -> Iterator[None]:
    """Push a request context (needed by tk.render / url_for) inside a worker."""
    if has_request_context():
        yield
        return

    flask_app = ckan.config.middleware.make_app(tk.config)
    with flask_app.test_request_context():
        yield


def _users(user_id: str) -> list[model.User]:
    user = model.User.get(user_id)
    return [user] if user else []


def _mail_users(users: Iterable[model.User], subject: str, template: str, extra_vars: dict[str, Any]) -> None:
    """Send one mail per recipient; a bad recipient doesn't stop the others."""
    ticket: DictizedTicket = extra_vars["ticket"]
    site_url = tk.config.get("ckan.site_url", "").rstrip("/")
    base_vars = {
        "site_title": tk.config.get("ckan.site_title", "CKAN"),
        "site_url": site_url,
        "ticket_url": site_url + tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
    }

    for user in users:
        if not user.email:
            log.info("[issues] %s has no email, skipping ticket #%s notification", user.name, ticket["id"])
            continue

        body = tk.render(template, extra_vars={**base_vars, **extra_vars, "recipient_name": user.display_name})

        log.info("[issues] Notifying %s about ticket #%s: %s", user.name, ticket["id"], subject)
        try:
            mailer.mail_user(user, subject=subject, body=body)
        except mailer.MailerException:
            log.exception("[issues] Failed to email %s about ticket #%s", user.name, ticket["id"])
