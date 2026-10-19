"""The ckanext-issues demo, recorded with ckan-demo.

    ckan-demo record demo/scenario.py --ckan-ini /path/to/ckan.ini --reset

See README.md in this folder.
"""

from __future__ import annotations

from ckan_demo import Director, Scenario, Setup, User
from playwright.sync_api import expect

from ckanext.issues.tests.e2e.sample_data import AUTHORS, STAFF

STAFF_NAME, STAFF_FULLNAME = next(iter(STAFF.items()))

DEMO_SUBJECT = "Population dataset is missing 2025 figures for three regions"
DEMO_TEXT = (
    "The **Population by region** dataset has no 2025 figures for:\n\n"
    "- Kharkiv\n- Odesa\n- Lviv\n\n"
    "Could you add them, or let us know when they will be published?"
)

scenario = Scenario(
    "ckanext-issues",
    users={
        "author": User("maria", fullname=AUTHORS["maria"]),
        "staff": User(STAFF_NAME, fullname=STAFF_FULLNAME, sysadmin=True),
        **{name: User(name, fullname=fullname) for name, fullname in AUTHORS.items() if name != "maria"},
    },
)


# ── Data ─────────────────────────────────────────────────────────────────────


@scenario.setup(local=True)
def prepare(setup: Setup) -> None:
    """Delete the last run's ticket (every ticket with --reset), then load the
    e2e sample backlog into an empty queue."""
    import sqlalchemy as sa

    from ckan import model

    from ckanext.issues.model import Ticket
    from ckanext.issues.tests.e2e import seed

    for ticket in model.Session.scalars(sa.select(Ticket)).all():
        if setup.reset or ticket.subject == DEMO_SUBJECT:
            setup.ckan.action.issues_ticket_delete(id=ticket.id)

    if model.Session.scalar(sa.select(sa.func.count()).select_from(Ticket)):
        return

    authors = {user["name"]: user for role, user in setup.users.items() if role != "staff"}
    seed.seed_tickets(authors, setup.users["staff"])


# ── Scenes ───────────────────────────────────────────────────────────────────


def ticket_url(d: Director, *, staff: bool = False) -> str:
    """URL of the demo ticket, looked up off camera (before ``d.goto``)."""
    listing = "/issues/admin/all" if staff else "/issues/my-tickets"
    d.page.goto(d.options.base_url + listing, wait_until="networkidle")
    return d.page.get_by_role("link", name=DEMO_SUBJECT).first.get_attribute("href") or ""


@scenario.scene("01-open-ticket", user="author")
def open_ticket(d: Director) -> None:
    """A user opens a ticket from the header and finds it in My tickets."""
    d.goto("/dataset/")
    d.card(
        "ckanext-issues",
        "Support tickets for CKAN",
        "Users ask for help on the portal. Staff answer and keep track.",
        hold=4,
    )

    d.caption("Signed-in users can open a ticket from the header", hold="read")
    d.click(d.page.get_by_role("button", name="New support ticket").first)
    modal = d.page.locator("#issues-ticket-modal")
    expect(modal.locator("#add-ticket-form")).to_be_visible()

    d.caption("Give it a subject, a category and a description. Markdown works", hold="read")
    d.type(modal.get_by_label("Subject"), DEMO_SUBJECT)
    d.select(modal.get_by_label("Category"), value="Data request")
    d.type(modal.get_by_label("Description"), DEMO_TEXT)

    d.caption("Submit, and the ticket is created", hold="read")
    d.click(modal.get_by_role("button", name="Submit"))
    expect(modal.get_by_role("heading", name="Your ticket has been successfully created")).to_be_visible()
    d.pause(2)

    with d.navigates():
        d.click(modal.get_by_role("link", name="View ticket"))
    d.caption("The ticket page shows its status, category and description", hold="read")

    d.caption("All your tickets are under “My tickets”", hold="read")
    with d.navigates():
        d.click(d.page.locator(".account-masthead").get_by_role("link", name="My tickets"))
    d.pause(3)
    d.caption(None, hold=0.5)


@scenario.scene("02-staff-triage", user="staff")
def staff_triage(d: Director) -> None:
    """Staff find it in Unassigned, take it and reply."""
    d.goto("/issues/admin/")
    d.card("Support staff", "The support queue", hold=2.5)

    d.caption("Staff see every open ticket here, with a count for each view", hold="read")
    tabs = d.page.get_by_role("navigation", name="Ticket views")
    d.caption("New tickets wait in “Unassigned”", hold="read")
    with d.navigates():
        d.click(tabs.get_by_role("link", name="Unassigned"))
    d.pause(1.5)

    with d.navigates():
        d.click(d.page.get_by_role("link", name=DEMO_SUBJECT))

    d.caption("Assign the ticket to yourself", hold="read")
    with d.navigates():
        d.select(d.page.locator("#assignee_id"), label=STAFF_FULLNAME)
    d.pause(1.5)

    d.caption("Reply on the ticket. Ctrl+Enter sends it", hold="read")
    reply = d.page.locator("#reply-textarea")
    d.type(
        reply,
        "Thanks, Maria! The 2025 regional figures are being validated. "
        "We expect to publish them **next week** and will update this ticket.",
    )
    d.press("Control+Enter")
    expect(d.page.locator(".message-card")).to_have_count(1)
    d.caption("Staff replies are marked “Support”", hold="read")
    d.caption(None, hold=0.3)


@scenario.scene("03-conversation", user="author")
def conversation(d: Director) -> None:
    """The user answers, then edits their message."""
    d.goto(ticket_url(d))
    d.card("Back to the user", "Following up", hold=2.5)

    d.caption("Maria sees the answer on her ticket", hold="read")
    reply = d.page.locator("#reply-textarea")
    d.type(reply, "Great, thank you! Could you also add the 2024 revisions?")
    d.press("Control+Enter")
    expect(d.page.locator(".message-card")).to_have_count(2)
    d.pause(1)

    d.caption("Authors can edit or delete their own messages", hold="read")
    own = d.page.locator(".message-card").last
    d.click(own.get_by_role("button", name="Edit message"))
    d.type(
        own.get_by_role("textbox", name="Edit message"),
        "Great, thank you! Could you also add the revised 2024 figures?",
        clear=True,
    )
    d.click(own.get_by_role("button", name="Save"))
    expect(own.locator(".msg-edited")).to_be_visible()
    d.pause(2.5)
    d.caption(None, hold=0.3)


@scenario.scene("04-staff-close", user="staff")
def staff_close(d: Director) -> None:
    """Staff close the ticket after a confirmation."""
    d.goto(ticket_url(d, staff=True))
    d.caption("Close the ticket when it's done. You'll be asked to confirm", hold="read")
    d.click(d.page.get_by_role("button", name="Close ticket"))
    dialog = d.page.locator("#ckan-confirm-modal")
    expect(dialog).to_be_visible()
    d.pause(1.5)
    with d.navigates():
        d.click(dialog.locator("#ckan-confirm-yes"))
    d.caption("A closed ticket is read-only. Staff can reopen it", hold="read")
    d.caption(None, hold=0.3)


@scenario.scene("05-author-closed", user="author")
def author_closed(d: Director) -> None:
    """The user sees the ticket is resolved."""
    d.goto(ticket_url(d))
    d.caption("Maria sees it's closed, and how to ask for more help", hold="read")
    d.point(d.page.locator(".ticket-closed-notice"))
    d.pause(3)
    d.caption(None, hold=0.3)


@scenario.scene("06-staff-manage", user="staff")
def staff_manage(d: Director) -> None:
    """Queue views, bulk actions, columns and the dark theme."""
    d.goto("/issues/admin/")
    d.card("Support staff", "Managing the queue", hold=2.5)

    tabs = d.page.get_by_role("navigation", name="Ticket views")
    d.caption("Closed tickets have their own view", hold="read")
    with d.navigates():
        d.click(tabs.get_by_role("link", name="Closed"))
    d.pause(2.5)
    with d.navigates():
        d.click(tabs.get_by_role("link", name="Open"))

    d.caption("Select several tickets to act on them at once", hold="read")
    for row in d.page.locator(".tabulator-row").all()[:2]:
        d.click(row.locator("input[type='checkbox']"))
    d.click(d.page.get_by_role("button", name="Bulk Actions"))
    d.pause(1)
    d.click(d.page.get_by_role("button", name="Delete selected tickets"))
    dialog = d.page.locator("#ckan-confirm-modal")
    expect(dialog.locator("#ckan-confirm-cancel")).to_be_focused()
    d.caption("Delete is shown in red, with Cancel selected", hold="read")
    d.press("Escape")
    expect(dialog).to_have_count(0)

    d.caption("Show or hide columns", hold="read")
    d.click(d.page.get_by_role("button", name="Columns"))
    columns = d.page.locator(".columns-modal")
    d.click(columns.locator("label", has=d.page.locator(".column-toggle[data-field='created_at']")))
    d.click(columns.locator("[id^='apply-columns-']"))
    d.pause(2)

    d.caption("There's a dark theme too", hold="read")
    d.click(d.page.get_by_role("button", name="Switch to dark theme"))
    d.pause(3)
    d.caption(None, hold=0.3)
    d.screenshot("dark-queue")
    d.card("", "ckanext-issues", "github.com/DataShades/ckanext-issues", hold=4)
