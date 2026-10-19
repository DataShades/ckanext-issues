"""Realistic sample tickets for browser tests and local demo data.

The same data set backs the e2e tests and can be loaded into a dev portal, so
screenshots taken by either look like a real support queue: several authors,
open and closed tickets, staff replies and backdated activity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ckan import model
from ckan.plugins import toolkit as tk

from ckanext.issues.model import Ticket
from ckanext.issues.tests.e2e.sample_data import AUTHORS, STAFF, TICKETS, TicketSpec

__all__ = ["AUTHORS", "STAFF", "TICKETS", "TicketSpec", "backdate", "seed_tickets"]


def _naive_utc(days_ago: float) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).replace(tzinfo=None)


def seed_tickets(authors: dict[str, dict[str, Any]], staff: dict[str, Any]) -> list[dict[str, Any]]:
    """Create ``TICKETS`` and return them as dictized tickets.

    ``authors`` maps the keys of ``AUTHORS`` to user dicts; ``staff`` is the
    sysadmin who replies and gets assigned. Timestamps are backdated so the
    UI shows a believable spread of "x days ago".
    """
    context: dict[str, Any] = {"ignore_auth": True}
    created: list[dict[str, Any]] = []

    for spec in TICKETS:
        author = authors[spec["author"]]
        ticket = tk.get_action("issues_ticket_create")(
            dict(context),
            {
                "subject": spec["subject"],
                "category": spec["category"],
                "text": spec["text"],
                "author_id": author["id"],
            },
        )

        for who, content in spec["messages"]:
            tk.get_action("issues_message_create")(
                dict(context),
                {
                    "ticket_id": ticket["id"],
                    "author_id": author["id"] if who == "author" else staff["id"],
                    "content": content,
                },
            )

        if spec["assignee"]:
            tk.get_action("issues_ticket_assign")(dict(context), {"id": ticket["id"], "assignee_id": staff["id"]})

        if spec["status"] != Ticket.Status.opened:
            tk.get_action("issues_ticket_update")(dict(context), {"id": ticket["id"], "status": spec["status"]})

        backdate(ticket["id"], spec["age_days"])
        created.append(tk.get_action("issues_ticket_show")(dict(context), {"id": ticket["id"]}))

    return created


def backdate(ticket_id: int, age_days: float) -> None:
    """Spread the ticket and its replies over the last ``age_days`` days."""
    ticket = Ticket.get(ticket_id)
    assert ticket

    created_at = _naive_utc(age_days)
    step = age_days / (len(ticket.messages) + 1)

    for index, message in enumerate(ticket.messages, start=1):
        message.created_at = _naive_utc(age_days - step * index)

    ticket.created_at = created_at
    ticket.updated_at = ticket.messages[-1].created_at if ticket.messages else created_at
    model.Session.commit()
