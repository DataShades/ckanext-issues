"""What a regular user sees: their ticket list, the new-ticket modal and threads."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page, expect

from ckan.tests import factories

from ckanext.issues.tests.e2e import seed
from ckanext.issues.tests.e2e.helpers import accept_confirm, confirm_dialog, find_ticket
from ckanext.issues.tests.factories import TicketFactory

Snap = Callable[[Page, str], None]


def _own_subjects(author: str) -> list[str]:
    return [spec["subject"] for spec in seed.TICKETS if spec["author"] == author]


def test_my_tickets_lists_only_own_tickets(login_as, authors, tickets, snap: Snap):
    page = login_as(authors["maria"])
    page.goto("/issues/my-tickets")

    rows = page.locator(".tabulator-row")
    expect(rows).to_have_count(len(_own_subjects("maria")))
    for subject in _own_subjects("maria"):
        expect(page.get_by_role("link", name=subject)).to_be_visible()
    expect(page.get_by_text(_own_subjects("tom")[0])).to_have_count(0)
    # The subject links to the ticket, so there is no extra row-actions menu.
    expect(page.locator(".btn-row-actions")).to_have_count(0)
    # Same status pill as on the ticket page.
    expect(page.locator(".tabulator-row .t-status-badge.status-closed")).to_have_text("Closed")

    snap(page, "list")


def test_my_tickets_empty_state(login_as, live_server, snap: Snap):
    page = login_as(factories.User(password="correct horse battery staple"))
    page.goto("/issues/my-tickets")

    expect(page.get_by_text("You haven't created any support tickets yet.")).to_be_visible()

    snap(page, "empty")


def test_create_ticket_from_modal(login_as, live_server, snap: Snap):
    page = login_as(factories.User(password="correct horse battery staple"))
    page.goto("/issues/my-tickets")

    page.get_by_role("button", name="New ticket").click()
    modal = page.locator("#issues-ticket-modal")
    expect(modal.get_by_role("heading", name="New support ticket")).to_be_visible()
    expect(modal.locator("#add-ticket-form")).to_be_visible()

    snap(page, "modal-empty")

    modal.get_by_label("Subject").fill("Map preview is blank for shapefiles")
    modal.get_by_label("Category").select_option("Bug report")
    modal.get_by_label("Description").fill("Zipped shapefiles show an empty map in the resource preview.")

    snap(page, "modal-filled")

    modal.get_by_role("button", name="Submit").click()
    expect(modal.get_by_role("heading", name="Your ticket has been successfully created")).to_be_visible()

    snap(page, "modal-success")

    modal.get_by_role("link", name="View ticket").click()
    expect(page.get_by_role("heading", name="Map preview is blank for shapefiles")).to_be_visible()
    expect(page.locator(".t-status-badge")).to_have_text("Open")
    expect(page.locator(".t-category-chip")).to_have_text("Bug report")


@pytest.mark.ckan_config("ckanext.issues.max_open_tickets_per_user", 1)
def test_open_ticket_limit_is_shown_in_modal(login_as, live_server):
    user = factories.User(password="correct horse battery staple")
    TicketFactory(author_id=user["id"])

    page = login_as(user)
    page.goto("/issues/my-tickets")
    page.get_by_role("button", name="New ticket").click()

    modal = page.locator("#issues-ticket-modal")
    modal.get_by_label("Subject").fill("One more")
    modal.get_by_label("Description").fill("Second open ticket")
    modal.get_by_role("button", name="Submit").click()

    expect(modal.get_by_role("alert")).to_contain_text("You already have 1 open support tickets")


def test_ticket_thread(login_as, authors, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Air quality dataset stopped updating after 3 March")
    page = login_as(authors["maria"])
    page.goto(f"/issues/ticket/{ticket['id']}")

    expect(page.locator(".message-card")).to_have_count(len(ticket["messages"]))
    expect(page.locator(".thread-count")).to_have_text(str(len(ticket["messages"])))
    # Regular users get no admin controls.
    expect(page.get_by_role("button", name="Close ticket")).to_have_count(0)
    expect(page.locator("#assignee_id")).to_have_count(0)
    # Replies from support staff are tagged; the author's own are not.
    staff_replies = sum(who == "staff" for who, _ in seed.TICKETS[0]["messages"])
    expect(page.locator(".msg-role")).to_have_count(staff_replies)
    expect(page.locator(".msg-role").first).to_have_text("Support")

    reply_label = page.locator("label[for='reply-textarea']")
    expect(reply_label).to_have_text("Reply")
    # CKAN suffixes every label with ":" via ::after; not this one.
    assert reply_label.evaluate("el => getComputedStyle(el, '::after').content") in {"none", "normal"}
    expect(page.locator("#reply-hint")).to_contain_text("Markdown supported")

    snap(page, "thread")


def test_reply_edit_and_delete_own_message(login_as, authors, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Request: monthly municipal budget data in CSV")
    page = login_as(authors["maria"])
    page.goto(f"/issues/ticket/{ticket['id']}")

    expect(page.get_by_text("No replies yet. Be the first to respond.")).to_be_visible()
    snap(page, "no-replies")

    reply = page.locator("#reply-textarea")
    reply.fill("Any update on this? Even a quarterly CSV would help.")
    page.get_by_role("button", name="Send Reply").click()

    message = page.locator(".message-card")
    expect(message).to_have_count(1)
    expect(message).to_contain_text("Even a quarterly CSV would help.")
    expect(page.locator(".thread-count")).to_have_text("1")
    expect(reply).to_have_value("")
    snap(page, "replied")

    message.get_by_role("button", name="Edit message").click()
    editor = message.get_by_role("textbox", name="Edit message")
    expect(editor).to_be_focused()
    editor.fill("Any update on this? A quarterly CSV would be fine too.")
    snap(page, "editing")
    message.get_by_role("button", name="Save").click()

    expect(message).to_contain_text("A quarterly CSV would be fine too.")
    expect(message.locator(".msg-edited")).to_be_visible()

    message.get_by_role("button", name="Delete message").click()
    dialog = confirm_dialog(page, "The message will be permanently removed from the conversation.")
    expect(dialog.locator(".modal-title")).to_have_text("Delete message?")
    expect(dialog.locator("#ckan-confirm-yes")).to_have_text("Delete message")
    snap(page, "confirm-delete")
    accept_confirm(page, "The message will be permanently removed from the conversation.")

    expect(page.locator(".message-card")).to_have_count(0)
    expect(page.locator(".thread-count")).to_have_text("0")


def test_ctrl_enter_sends_reply(login_as, authors, tickets):
    ticket = find_ticket(tickets, "Request: monthly municipal budget data in CSV")
    page = login_as(authors["maria"])
    page.goto(f"/issues/ticket/{ticket['id']}")

    page.locator("#reply-textarea").fill("Sent from the keyboard")
    page.locator("#reply-textarea").press("Control+Enter")

    expect(page.locator(".message-card")).to_contain_text("Sent from the keyboard")


def test_closed_ticket_has_no_reply_form(login_as, authors, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Typo in the organisation description")
    page = login_as(authors["maria"])
    page.goto(f"/issues/ticket/{ticket['id']}")

    expect(page.locator(".t-status-badge")).to_have_text("Closed")
    expect(page.get_by_text("This ticket is closed.")).to_be_visible()
    expect(page.get_by_text("Open a new ticket if you need further help.")).to_be_visible()
    expect(page.locator("#reply-form")).to_have_count(0)
    # Messages on closed tickets are read-only.
    expect(page.get_by_role("button", name="Edit message")).to_have_count(0)

    snap(page, "closed")


def test_cannot_open_someone_elses_ticket(login_as, authors, tickets):
    ticket = find_ticket(tickets, _own_subjects("tom")[0])
    page = login_as(authors["maria"])

    response = page.goto(f"/issues/ticket/{ticket['id']}")

    assert response
    assert response.status == 403


def test_ticket_page_on_mobile(login_as, authors, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Air quality dataset stopped updating after 3 March")
    page = login_as(authors["maria"], viewport={"width": 390, "height": 844})
    page.goto(f"/issues/ticket/{ticket['id']}")

    expect(page.get_by_role("heading", name=ticket["subject"])).to_be_visible()
    # Nothing should force a horizontal scroll on a phone.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    # Reading order on one column: title, then details, then the description.
    title = page.locator(".ticket-header-card").bounding_box()
    details = page.locator(".ticket-sidebar").bounding_box()
    body = page.locator(".ticket-body-card").bounding_box()
    assert title
    assert details
    assert body
    assert title["y"] < details["y"] < body["y"]

    snap(page, "mobile")
