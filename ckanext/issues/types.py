from typing import TypedDict


class DictizedUser(TypedDict):
    id: str
    name: str
    display_name: str


class TicketData(TypedDict):
    subject: str
    text: str
    author_id: str
    category: str


class DictizedMessage(TypedDict):
    id: int
    ticket_id: int
    content: str
    author: DictizedUser
    created_at: str
    updated_at: str | None


class DictizedTicket(TypedDict):
    id: int
    category: str
    subject: str
    status: str
    text: str
    author: DictizedUser
    assignee: DictizedUser | None
    created_at: str
    updated_at: str
    messages: list[DictizedMessage]
