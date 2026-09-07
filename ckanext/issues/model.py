from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, backref, relationship
from typing_extensions import Self

from ckan import model, types
from ckan.plugins import toolkit as tk

from ckanext.issues.types import DictizedMessage, DictizedTicket, TicketData

log = logging.getLogger(__name__)


def _as_pk(value: Any) -> int | None:
    """Coerce a value (often a raw URL segment) to an integer primary key.

    Returns ``None`` for anything that is not a plain integer, so a bogus id
    such as ``/issues/ticket/abc`` becomes a clean "not found" rather than a
    database ``DataError``.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class Ticket(tk.BaseModel):
    class Status:
        opened = "opened"
        closed = "closed"

    __table__ = sa.Table(
        "issues_ticket",
        tk.BaseModel.metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("subject", sa.Text),
        sa.Column("status", sa.Text, default=Status.opened),
        sa.Column("text", sa.Text),
        sa.Column("category", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column("author_id", sa.Text, sa.ForeignKey("user.id"), nullable=False),
        sa.Column(
            "assignee_id",
            sa.Text,
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    id: Mapped[int]
    subject: Mapped[str | None]
    status: Mapped[str | None]
    text: Mapped[str | None]
    category: Mapped[str | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    author_id: Mapped[str]
    assignee_id: Mapped[str | None]

    author: Mapped[model.User] = relationship(
        model.User,
        foreign_keys="Ticket.author_id",
        backref=backref("issues_tickets", cascade="all, delete"),
    )

    # Deleting the assignee must NOT delete their tickets — just unassign them.
    # (nullify on the ORM side; ON DELETE SET NULL covers raw-SQL deletes)
    assignee: Mapped[model.User | None] = relationship(
        model.User,
        foreign_keys="Ticket.assignee_id",
        backref=backref("issues_assigned_tickets", passive_deletes=True),
    )

    messages: Mapped[list[TicketMessage]] = relationship(
        "TicketMessage",
        order_by="TicketMessage.created_at",
        cascade="all, delete",
        back_populates="ticket",
    )

    def __str__(self) -> str:
        return f"Ticket #{self.id}: {self.subject}"

    @classmethod
    def get(cls, ticket_id: Any) -> Self | None:
        pk = _as_pk(ticket_id)
        return model.Session.get(cls, pk) if pk is not None else None

    @classmethod
    def count_open_for_author(cls, author_id: str) -> int:
        stmt = (
            sa.select(sa.func.count())
            .select_from(cls)
            .where(cls.author_id == author_id, cls.status == cls.Status.opened)
        )
        return model.Session.scalar(stmt) or 0

    def delete(self) -> None:
        model.Session.delete(self)

    @classmethod
    def add(cls, ticket_data: TicketData) -> DictizedTicket:
        ticket = cls(
            subject=ticket_data["subject"],
            category=ticket_data["category"],
            text=ticket_data["text"],
            author_id=ticket_data["author_id"],
        )

        model.Session.add(ticket)
        model.Session.commit()

        return ticket.dictize({})

    def dictize(self, context: types.Context) -> DictizedTicket:
        return DictizedTicket(
            id=self.id,
            subject=self.subject or "",
            category=self.category or "",
            status=self.status or "",
            text=self.text or "",
            author=self.author.as_dict(),
            assignee=self.assignee.as_dict() if self.assignee else None,
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat(),
            messages=[msg.dictize(context) for msg in self.messages],
        )


class TicketMessage(tk.BaseModel):
    __table__ = sa.Table(
        "issues_ticket_message",
        tk.BaseModel.metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "ticket_id",
            sa.Integer,
            sa.ForeignKey("issues_ticket.id"),
            nullable=False,
        ),
        sa.Column("author_id", sa.Text, sa.ForeignKey("user.id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime, nullable=True),
    )

    id: Mapped[int]
    ticket_id: Mapped[int]
    author_id: Mapped[str]
    content: Mapped[str]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime | None]

    author: Mapped[model.User] = relationship(model.User)
    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="messages")

    @classmethod
    def get(cls, message_id: Any) -> Self | None:
        pk = _as_pk(message_id)
        return model.Session.get(cls, pk) if pk is not None else None

    @classmethod
    def add(cls, ticket_id: int, author_id: str, content: str) -> Self:
        message = cls(ticket_id=ticket_id, author_id=author_id, content=content)
        model.Session.add(message)
        model.Session.commit()

        return message

    def delete(self) -> None:
        ticket = self.ticket
        if ticket is not None and self in ticket.messages:
            ticket.messages.remove(self)
        model.Session.delete(self)

    def update(self, content: str) -> None:
        self.content = content
        self.updated_at = datetime.utcnow()

    def dictize(self, context: types.Context) -> DictizedMessage:
        return DictizedMessage(
            id=self.id,
            ticket_id=self.ticket_id,
            content=self.content,
            author=self.author.as_dict(),
            created_at=self.created_at.isoformat(),
            updated_at=self.updated_at.isoformat() if self.updated_at else None,
        )
