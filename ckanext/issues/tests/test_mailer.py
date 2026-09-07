from __future__ import annotations

import pytest

from ckan.tests import factories
from ckan.tests.helpers import call_action

TICKET = {"subject": "Help", "text": "please", "category": "Bug report"}

new_ticket = pytest.mark.ckan_config("ckanext.issues.notify_on_new_ticket", "true")
new_message = pytest.mark.ckan_config("ckanext.issues.notify_on_new_message", "true")
ticket_update = pytest.mark.ckan_config("ckanext.issues.notify_on_ticket_update", "true")


@pytest.mark.usefixtures("with_plugins", "clean_db", "with_request_context")
class TestNotifications:
    @new_ticket
    def test_new_ticket_emails_active_sysadmins(self, mail_server):
        sysadmin = factories.Sysadmin()
        author = factories.User()

        call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        messages = mail_server.get_smtp_messages()
        assert len(messages) == 1
        assert sysadmin["email"] in messages[0][2]
        assert "New support ticket" in messages[0][3]

    def test_new_ticket_notification_is_off_by_default(self, mail_server):
        factories.Sysadmin()
        author = factories.User()

        call_action("issues_ticket_create", author_id=author["id"], **TICKET)

        assert mail_server.get_smtp_messages() == []

    @new_message
    def test_reply_emails_the_ticket_author(self, mail_server):
        author = factories.User()
        staff = factories.User()
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

    @ticket_update
    def test_ticket_update_emails_the_author(self, mail_server):
        author = factories.User()
        sysadmin = factories.Sysadmin()
        ticket = call_action("issues_ticket_create", author_id=author["id"], **TICKET)
        mail_server.clear_smtp_messages()

        call_action(
            "issues_ticket_update",
            context={"user": sysadmin["name"]},
            id=ticket["id"],
            status="closed",
        )

        messages = mail_server.get_smtp_messages()
        assert len(messages) == 1
        assert author["email"] in messages[0][2]
