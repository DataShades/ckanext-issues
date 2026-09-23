from __future__ import annotations

import email
from typing import TYPE_CHECKING

import pytest

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.lib import mailer as ckan_mailer
from ckan.tests import factories
from ckan.tests.helpers import call_action

from ckanext.issues import mailer

if TYPE_CHECKING:
    from email.message import Message

TICKET = {"subject": "Help", "text": "please", "category": "Bug report"}

new_ticket = pytest.mark.ckan_config("ckanext.issues.notify_on_new_ticket", "true")
new_message = pytest.mark.ckan_config("ckanext.issues.notify_on_new_message", "true")
ticket_update = pytest.mark.ckan_config("ckanext.issues.notify_on_ticket_update", "true")
ticket_assign = pytest.mark.ckan_config("ckanext.issues.notify_on_ticket_assign", "true")


@pytest.fixture
def sync_jobs(monkeypatch):
    """Run enqueued jobs inline instead of through a worker."""

    def enqueue(fn, args=None, kwargs=None, **_):
        fn(*(args or []), **(kwargs or {}))

    monkeypatch.setattr(tk, "enqueue_job", enqueue)


@pytest.fixture
def enqueued(monkeypatch):
    """Capture enqueued jobs without running them."""
    jobs = []
    monkeypatch.setattr(tk, "enqueue_job", lambda fn, args=None, **kw: jobs.append((fn, args, kw)))
    return jobs


def _parsed(mail_server) -> list[Message]:
    return [email.message_from_string(m[3]) for m in mail_server.get_smtp_messages()]


def _subjects(mail_server) -> list[str]:
    return [str(msg["Subject"]) for msg in _parsed(mail_server)]


def _bodies(mail_server) -> list[str]:
    """Decoded text bodies (non-ASCII mails are sent base64-encoded)."""
    return [msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8") for msg in _parsed(mail_server)]


@pytest.mark.usefixtures("with_plugins", "clean_db", "with_request_context", "sync_jobs")
class TestNotifications:
    @new_ticket
    def test_new_ticket_emails_active_sysadmins(self, mail_server):
        sysadmin = factories.Sysadmin()
        author = factories.User()

        call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        recipients = [m[2] for m in mail_server.get_smtp_messages()]
        assert any(sysadmin["email"] in r for r in recipients)
        assert all("New support ticket" in s for s in _subjects(mail_server))

    @new_ticket
    def test_new_ticket_submitted_date_is_human_readable(self, mail_server):
        factories.Sysadmin()
        author = factories.User()

        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        body = _bodies(mail_server)[0]
        assert ticket["created_at"] not in body
        assert tk.h.render_datetime(ticket["created_at"], with_hours=True) in body

    def test_new_ticket_notification_is_off_by_default(self, mail_server):
        factories.Sysadmin()
        author = factories.User()

        call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        assert mail_server.get_smtp_messages() == []

    @new_message
    def test_reply_emails_the_ticket_author(self, mail_server):
        author = factories.User()
        staff = factories.Sysadmin()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)
        mail_server.clear_smtp_messages()

        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=staff["id"],
            content="looking into it",
        )

        messages = mail_server.get_smtp_messages()
        assert len(messages) == 1
        assert author["email"] in messages[0][2]

    @new_message
    def test_author_replying_to_own_ticket_is_not_emailed(self, mail_server):
        author = factories.User()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)
        mail_server.clear_smtp_messages()

        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=author["id"],
            content="a note",
        )

        assert mail_server.get_smtp_messages() == []

    @new_message
    def test_author_without_email_is_skipped(self, mail_server):
        author = factories.User()
        staff = factories.Sysadmin()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)
        user = model.User.get(author["id"])
        user.email = ""
        model.Session.commit()

        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=staff["id"],
            content="looking into it",
        )

        assert mail_server.get_smtp_messages() == []

    @ticket_update
    def test_ticket_update_emails_the_author(self, mail_server):
        author = factories.User()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)
        mail_server.clear_smtp_messages()

        call_action("issues_ticket_update", id=ticket["id"], status="closed")

        messages = mail_server.get_smtp_messages()
        assert len(messages) == 1
        assert author["email"] in messages[0][2]

    @ticket_update
    def test_no_op_update_sends_nothing(self, mail_server):
        author = factories.User()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        call_action("issues_ticket_update", id=ticket["id"], status="opened")

        assert mail_server.get_smtp_messages() == []

    @ticket_assign
    def test_assign_emails_the_assignee(self, mail_server):
        author = factories.User()
        staff = factories.Sysadmin()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        call_action("issues_ticket_assign", id=ticket["id"], assignee_id=staff["id"])

        messages = mail_server.get_smtp_messages()
        assert len(messages) == 1
        assert staff["email"] in messages[0][2]
        assert "assigned to you" in _subjects(mail_server)[0]

    @ticket_update
    def test_status_is_human_readable(self, mail_server):
        author = factories.User()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        call_action("issues_ticket_update", id=ticket["id"], status="closed")

        body = _bodies(mail_server)[0]
        assert "Status: Closed" in body

    @ticket_update
    def test_plain_text_body_is_not_html_escaped(self, mail_server):
        author = factories.User()
        ticket = call_action(
            "issues_ticket_create",
            author_id=author["id"],
            **{**TICKET, "subject": "Tom & Jerry <script>"},
        )

        call_action("issues_ticket_update", id=ticket["id"], status="closed")

        body = _bodies(mail_server)[0]
        assert "&amp;" not in body
        assert "&lt;" not in body

    @ticket_update
    def test_smtp_failure_does_not_fail_the_action(self, monkeypatch):
        def boom(*args, **kwargs):
            msg = "smtp down"
            raise ckan_mailer.MailerException(msg)

        monkeypatch.setattr(ckan_mailer, "mail_user", boom)
        author = factories.User()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        result = call_action("issues_ticket_update", id=ticket["id"], status="closed")

        assert result["status"] == "closed"


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDeferredSending:
    @new_ticket
    @new_message
    @ticket_update
    @ticket_assign
    def test_actions_only_enqueue_and_need_no_request_context(self, enqueued):
        author = factories.User()
        staff = factories.Sysadmin()

        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)
        call_action("issues_message_create", ticket_id=ticket["id"], author_id=staff["id"], content="hi")
        call_action("issues_ticket_assign", id=ticket["id"], assignee_id=staff["id"])

        assert {kw["queue"] for _, _, kw in enqueued} == {"default"}
        jobs = [fn for fn, _, _ in enqueued]
        assert jobs == [
            mailer.send_new_ticket_emails,
            mailer.send_new_message_email,
            mailer.send_ticket_updated_email,
            mailer.send_ticket_assigned_email,
        ]

    @new_ticket
    @pytest.mark.ckan_config("ckanext.issues.mail_queue", "issues_mail")
    def test_mails_go_to_the_configured_queue(self, enqueued):
        author = factories.User()

        call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        assert [kw["queue"] for _, _, kw in enqueued] == ["issues_mail"]
