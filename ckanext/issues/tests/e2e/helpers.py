from __future__ import annotations

from typing import Any

from playwright.sync_api import Locator, Page, expect


def confirm_dialog(page: Page, question: str) -> Locator:
    """Return CKAN's confirm modal (it replaces ``hx-confirm``'s window.confirm)."""
    dialog = page.locator("#ckan-confirm-modal")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text(question)
    return dialog


def accept_confirm(page: Page, question: str) -> None:
    confirm_dialog(page, question).locator("#ckan-confirm-yes").click()


def find_ticket(tickets: list[dict[str, Any]], subject: str) -> dict[str, Any]:
    """Pick a seeded ticket by subject."""
    return next(ticket for ticket in tickets if ticket["subject"] == subject)
