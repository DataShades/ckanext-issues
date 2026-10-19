"""What support staff (sysadmins) see: the support queue and ticket management."""

from __future__ import annotations

import re
from collections.abc import Callable

from playwright.sync_api import Page, expect

from ckanext.issues.tests.e2e import seed
from ckanext.issues.tests.e2e.helpers import accept_confirm, confirm_dialog, find_ticket

Snap = Callable[[Page, str], None]

OPEN = [spec["subject"] for spec in seed.TICKETS if spec["status"] == "opened"]
CLOSED = [spec["subject"] for spec in seed.TICKETS if spec["status"] == "closed"]


def _tab(page: Page, label: str):
    return page.get_by_role("navigation", name="Ticket views").get_by_role("link", name=re.compile(rf"^{label}\b"))


def test_support_queue_opens_on_open_tickets(login_as, staff, tickets, snap: Snap):
    page = login_as(staff)
    page.goto("/issues/admin/")

    expect(_tab(page, "Open")).to_have_attribute("aria-current", "page")
    expect(page.locator(".tabulator-row")).to_have_count(len(OPEN))
    for subject in OPEN:
        expect(page.get_by_role("link", name=subject)).to_be_visible()
    for subject in CLOSED:
        expect(page.get_by_role("link", name=subject)).to_have_count(0)

    assigned_to_staff = [s for s in seed.TICKETS if s["status"] == "opened" and s["assignee"]]
    for label, count in (
        ("Open", len(OPEN)),
        ("Unassigned", len(OPEN) - len(assigned_to_staff)),
        ("Assigned to me", len(assigned_to_staff)),
        ("Closed", len(CLOSED)),
        ("All", len(seed.TICKETS)),
    ):
        expect(_tab(page, label).locator(".issues-tab-count")).to_have_text(str(count))

    snap(page, "queue")


def test_switch_support_queue_tabs(login_as, staff, tickets, snap: Snap):
    page = login_as(staff)
    page.goto("/issues/admin/")

    _tab(page, "Closed").click()
    expect(page).to_have_url(re.compile(r"/issues/admin/closed$"))
    expect(_tab(page, "Closed")).to_have_attribute("aria-current", "page")
    expect(page.locator(".tabulator-row")).to_have_count(len(CLOSED))
    for subject in CLOSED:
        expect(page.get_by_role("link", name=subject)).to_be_visible()
    snap(page, "closed")

    _tab(page, "All").click()
    expect(page.locator(".tabulator-row")).to_have_count(len(seed.TICKETS))


def test_support_queue_tabs_on_mobile(login_as, staff, tickets, snap: Snap):
    page = login_as(staff, viewport={"width": 390, "height": 844})
    page.goto("/issues/admin/")

    expect(_tab(page, "Open")).to_be_visible()
    # The tab strip scrolls on its own; the page must not.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    snap(page, "mobile")


def test_created_column_hidden_by_default(login_as, staff, tickets):
    page = login_as(staff)
    page.goto("/issues/admin/")
    expect(page.locator(".tabulator-row")).to_have_count(len(OPEN))

    created = page.locator(".tabulator-col[tabulator-field='created_at']")
    expect(created).to_be_hidden()
    expect(page.locator(".tabulator-col[tabulator-field='updated_at']")).to_be_visible()
    # The Columns button flags the hidden column, as it does for ones hidden by hand.
    badge = page.locator("[id^='hidden-columns-badge-']")
    expect(badge).to_be_visible()
    expect(badge).to_have_text("1")

    page.get_by_role("button", name="Columns").click()
    columns = page.locator(".columns-modal")
    toggle = columns.locator(".column-toggle[data-field='created_at']")
    expect(toggle).not_to_be_checked()
    toggle.check()
    columns.locator("[id^='apply-columns-']").click()

    expect(created).to_be_visible()
    expect(badge).to_be_hidden()

    # Reset goes back to the defaults, so Created is hidden again.
    page.get_by_role("button", name="Columns").click()
    columns.locator("[id^='reset-columns-']").click()
    expect(created).to_be_hidden()
    expect(badge).to_have_text("1")


def test_support_queue_header_link(login_as, staff, tickets):
    page = login_as(staff)
    page.goto("/")

    page.get_by_role("link", name="Support tickets").click()

    expect(page).to_have_url(re.compile(r"/issues/admin/"))
    expect(page.get_by_role("heading", name="Support tickets")).to_be_visible()


def test_regular_user_cannot_open_support_queue(login_as, authors, tickets):
    page = login_as(authors["tom"])

    response = page.goto("/issues/admin/")

    assert response
    assert response.status == 403


def test_bulk_close_tickets(login_as, staff, tickets, snap: Snap):
    page = login_as(staff)
    page.goto("/issues/admin/")

    open_subjects = OPEN[:2]
    for subject in open_subjects:
        row = page.locator(".tabulator-row", has=page.get_by_role("link", name=subject))
        row.locator("input[type='checkbox']").check()

    page.get_by_role("button", name="Bulk Actions").click()
    snap(page, "bulk-menu")
    page.get_by_role("button", name="Close selected tickets").click()
    dialog = confirm_dialog(page, "Authors of the selected tickets will no longer be able to reply.")
    expect(dialog.locator(".modal-title")).to_have_text("Close tickets?")
    expect(dialog.locator("#ckan-confirm-yes")).to_have_text("Close tickets")
    expect(dialog.locator("#ckan-confirm-yes")).not_to_have_class(re.compile(r"\bbtn-danger\b"))
    accept_confirm(page, "Authors of the selected tickets will no longer be able to reply.")

    # Closed tickets leave the open queue…
    expect(page.locator(".tabulator-row")).to_have_count(len(OPEN) - len(open_subjects))
    for subject in open_subjects:
        expect(page.get_by_role("link", name=subject)).to_have_count(0)

    # …and turn up under Closed.
    page.goto("/issues/admin/closed")
    for subject in open_subjects:
        row = page.locator(".tabulator-row", has=page.get_by_role("link", name=subject))
        expect(row).to_contain_text("Closed", ignore_case=True)


def test_bulk_delete_confirm_is_destructive(login_as, staff, tickets, snap: Snap):
    page = login_as(staff)
    page.goto("/issues/admin/")
    page.locator(".tabulator-row input[type='checkbox']").first.check()

    page.get_by_role("button", name="Bulk Actions").click()
    page.get_by_role("button", name="Delete selected tickets").click()

    dialog = confirm_dialog(page, "The selected tickets and their conversations will be permanently deleted.")
    expect(dialog.locator(".modal-title")).to_have_text("Delete tickets?")
    expect(dialog.locator(".modal-title")).to_have_css("color", "rgb(255, 255, 255)")
    expect(dialog.locator("#ckan-confirm-yes")).to_have_text("Delete tickets")
    expect(dialog.locator("#ckan-confirm-yes")).to_have_class(re.compile(r"\bbtn-danger\b"))
    expect(dialog.locator("#ckan-confirm-cancel")).to_be_focused()
    snap(page, "confirm")

    page.keyboard.press("Escape")
    expect(page.locator("#ckan-confirm-modal")).to_have_count(0)
    expect(page.locator(".tabulator-row")).to_have_count(len(OPEN))


def test_row_delete_from_actions_menu(login_as, staff, tickets):
    ticket = find_ticket(tickets, "Dark mode makes chart labels unreadable")
    page = login_as(staff)
    page.goto("/issues/admin/")

    row = page.locator(".tabulator-row", has=page.get_by_role("link", name=ticket["subject"]))
    row.locator(".btn-row-actions").click()
    page.locator(".tabulator-menu-item", has_text="Delete").click()

    dialog = confirm_dialog(page, "The ticket and its whole conversation will be permanently deleted.")
    expect(dialog.locator(".modal-title")).to_have_text("Delete ticket?")
    expect(dialog.locator("#ckan-confirm-yes")).to_have_class(re.compile(r"\bbtn-danger\b"))
    accept_confirm(page, "The ticket and its whole conversation will be permanently deleted.")

    expect(page.locator(".tabulator-row")).to_have_count(len(OPEN) - 1)
    expect(page.get_by_role("link", name=ticket["subject"])).to_have_count(0)


def test_staff_ticket_view(login_as, staff, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Air quality dataset stopped updating after 3 March")
    page = login_as(staff)
    page.goto(f"/issues/ticket/{ticket['id']}")

    expect(page.locator("#assignee_id")).to_be_visible()
    expect(page.get_by_role("button", name="Close ticket")).to_be_visible()
    expect(page.get_by_role("button", name="Delete ticket")).to_be_visible()
    # Staff may manage every message, not only their own.
    expect(page.get_by_role("button", name="Edit message")).to_have_count(len(ticket["messages"]))

    snap(page, "ticket")


def test_assign_and_unassign(login_as, staff, tickets):
    ticket = find_ticket(tickets, "Request: monthly municipal budget data in CSV")
    page = login_as(staff)
    page.goto(f"/issues/ticket/{ticket['id']}")

    # Each change reloads the page (HX-Redirect); wait for the reload to finish
    # so htmx is bound again before the next interaction.
    with page.expect_navigation():
        page.locator("#assignee_id").select_option(label=staff["fullname"])

    expect(page.locator(".ticket-meta-row")).to_contain_text(f"Assigned to {staff['fullname']}")
    expect(page.locator("#assignee_id")).to_have_value(staff["id"])

    with page.expect_navigation():
        page.locator("#assignee_id").select_option(label="Unassigned")

    expect(page.locator(".ticket-meta-row")).not_to_contain_text("Assigned to")


def test_close_and_reopen(login_as, staff, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Bulk download for all transport datasets")
    page = login_as(staff)
    page.goto(f"/issues/ticket/{ticket['id']}")

    page.get_by_role("button", name="Close ticket").click()
    with page.expect_navigation():
        accept_confirm(page, "The author will no longer be able to reply.")

    expect(page.locator(".t-status-badge")).to_have_text("Closed")
    expect(page.get_by_text("Reopen the ticket to add new replies.")).to_be_visible()
    expect(page.locator("#reply-form")).to_have_count(0)
    snap(page, "closed")

    page.get_by_role("button", name="Reopen ticket").click()
    with page.expect_navigation():
        accept_confirm(page, "The conversation will be open for replies again.")

    expect(page.locator(".t-status-badge")).to_have_text("Open")
    expect(page.locator("#reply-form")).to_be_visible()


def test_staff_reply_is_visible_to_author(login_as, staff, authors, tickets):
    ticket = find_ticket(tickets, "Bulk download for all transport datasets")

    staff_page = login_as(staff)
    staff_page.goto(f"/issues/ticket/{ticket['id']}")
    staff_page.locator("#reply-textarea").fill("We have added this to the roadmap for Q3.")
    staff_page.get_by_role("button", name="Send Reply").click()
    expect(staff_page.locator(".message-card")).to_have_count(1)

    author_page = login_as(authors["tom"])
    author_page.goto(f"/issues/ticket/{ticket['id']}")

    message = author_page.locator(".message-card")
    expect(message).to_contain_text("We have added this to the roadmap for Q3.")
    expect(message.locator(".msg-bubble")).to_have_class("msg-bubble bbl-staff")
    expect(message.locator(".msg-role")).to_have_text("Support")


def test_close_confirm_is_not_styled_as_destructive(login_as, staff, tickets):
    ticket = find_ticket(tickets, "Bulk download for all transport datasets")
    page = login_as(staff)
    page.goto(f"/issues/ticket/{ticket['id']}")

    page.get_by_role("button", name="Close ticket").click()
    dialog = confirm_dialog(page, "The author will no longer be able to reply.")
    expect(dialog.locator(".modal-title")).to_have_text("Close ticket?")
    expect(dialog.locator("#ckan-confirm-yes")).to_have_text("Close ticket")
    expect(dialog.locator("#ckan-confirm-yes")).not_to_have_class(re.compile(r"\bbtn-danger\b"))


def test_escape_cancels_delete(login_as, staff, tickets):
    ticket = find_ticket(tickets, "Dark mode makes chart labels unreadable")
    page = login_as(staff)
    page.goto(f"/issues/ticket/{ticket['id']}")

    page.get_by_role("button", name="Delete ticket").click()
    dialog = confirm_dialog(page, "permanently deleted")
    # Shown (Bootstrap ignores Escape while the dialog is still fading in).
    expect(dialog.locator("#ckan-confirm-cancel")).to_be_focused()
    page.keyboard.press("Escape")

    expect(page.locator("#ckan-confirm-modal")).to_have_count(0)
    page.reload()
    expect(page.get_by_role("heading", name=ticket["subject"])).to_be_visible()


def test_delete_ticket(login_as, staff, tickets, snap: Snap):
    ticket = find_ticket(tickets, "Dark mode makes chart labels unreadable")
    page = login_as(staff)
    page.goto(f"/issues/ticket/{ticket['id']}")

    page.get_by_role("button", name="Delete ticket").click()
    dialog = confirm_dialog(page, "The ticket and its whole conversation will be permanently deleted.")
    expect(dialog.locator(".modal-title")).to_have_text("Delete ticket?")
    # Core's red header with a readable white title (CKAN's theme colours
    # .modal-title navy unless our override applies).
    expect(dialog.locator(".modal-header")).to_have_class(re.compile(r"\bbg-danger\b"))
    expect(dialog.locator(".modal-title")).to_have_css("color", "rgb(255, 255, 255)")
    confirm = dialog.locator("#ckan-confirm-yes")
    expect(confirm).to_have_text("Delete ticket")
    expect(confirm).to_have_class(re.compile(r"\bbtn-danger\b"))
    # Destructive: start on Cancel so Enter does not delete.
    expect(dialog.locator("#ckan-confirm-cancel")).to_be_focused()
    snap(page, "confirm")
    accept_confirm(page, "The ticket and its whole conversation will be permanently deleted.")

    expect(page).to_have_url(re.compile(r"/issues/admin/"))
    expect(page.get_by_text("The ticket has been deleted")).to_be_visible()
    expect(page.locator(".tabulator-row")).to_have_count(len(OPEN) - 1)
    expect(page.get_by_role("link", name=ticket["subject"])).to_have_count(0)
