from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests.helpers import call_action

from ckanext.issues.model import Ticket

if TYPE_CHECKING:
    from ckanext.issues.types import DictizedTicket


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTicketCreate:
    def test_basic_create(self, ticket_factory):
        """Test creating a ticket with basic fields."""
        ticket: DictizedTicket = ticket_factory()

        assert ticket["id"]
        assert ticket["subject"]
        assert ticket["text"]
        assert ticket["category"]
        assert ticket["author"]
        assert ticket["created_at"]
        assert ticket["updated_at"]
        assert ticket["status"] == Ticket.Status.opened
        assert ticket["messages"] == []

    @pytest.mark.ckan_config("ckanext.issues.category_list", "general")
    def test_create_with_custom_category(self, user):
        """Test creating a ticket with a category from the configured list."""
        ticket: DictizedTicket = call_action(
            "issues_ticket_create",
            subject="Test Subject",
            text="Test text",
            category="general",
            author_id=user["id"],
        )

        assert ticket["category"] == "general"


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTicketShow:
    def test_show_ticket(self, ticket):
        """Test retrieving a ticket by ID."""
        result: DictizedTicket = call_action("issues_ticket_show", id=ticket["id"])

        assert result["id"] == ticket["id"]
        assert result["subject"] == ticket["subject"]

    def test_show_nonexistent_ticket(self):
        """Test that showing a non-existent ticket raises an error."""
        with pytest.raises(tk.ValidationError, match="Ticket not found"):
            call_action("issues_ticket_show", id="999999")


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTicketUpdate:
    @pytest.mark.usefixtures("with_request_context")
    def test_update_status(self, ticket, sysadmin, mail_server):
        """Test updating a ticket's status."""
        context = {"user": sysadmin["name"], "model": model}

        result = call_action(
            "issues_ticket_update",
            context=context,
            id=ticket["id"],
            status=Ticket.Status.closed,
        )

        assert result["status"] == Ticket.Status.closed

        # Verify the update
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        assert updated_ticket["status"] == Ticket.Status.closed

    def test_update_nonexistent_ticket(self, sysadmin):
        """Test updating a non-existent ticket raises an error."""
        context = {"user": sysadmin["name"], "model": model}

        with pytest.raises(tk.ValidationError, match="Ticket not found"):
            call_action(
                "issues_ticket_update",
                context=context,
                id="999999",
                status=Ticket.Status.closed,
            )


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTicketDelete:
    def test_delete_ticket(self, ticket, sysadmin):
        """Test deleting a ticket."""
        context = {"user": sysadmin["name"], "model": model}

        result = call_action(
            "issues_ticket_delete",
            context=context,
            id=ticket["id"],
        )

        assert result is True

        # Verify the ticket is deleted
        with pytest.raises(tk.ValidationError, match="Ticket not found"):
            call_action("issues_ticket_show", id=ticket["id"])

    def test_delete_nonexistent_ticket(self, sysadmin):
        """Test deleting a non-existent ticket raises an error."""
        context = {"user": sysadmin["name"], "model": model}

        with pytest.raises(tk.ValidationError, match="Ticket not found"):
            call_action(
                "issues_ticket_delete",
                context=context,
                id="999999",
            )

    def test_delete_without_id_raises_not_found(self, sysadmin):
        """A missing id must not blow up (the schema allows it) — it 404s."""
        context = {"user": sysadmin["name"], "model": model}

        with pytest.raises(tk.ObjectNotFound):
            call_action("issues_ticket_delete", context=context)


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageCreate:
    @pytest.mark.usefixtures("with_request_context")
    def test_create_message(self, ticket, user, mail_server):
        """Test creating a message on an opened ticket."""
        result = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="This is a test message",
        )

        assert result["content"] == "This is a test message"

        # Verify the message was added
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        assert len(updated_ticket["messages"]) == 1
        assert updated_ticket["messages"][0]["content"] == "This is a test message"

    @pytest.mark.usefixtures("with_request_context")
    def test_create_message_on_closed_ticket(self, ticket, user, sysadmin, mail_server):
        """Test that creating a message on a closed ticket fails."""
        # Close the ticket
        context = {"user": sysadmin["name"], "model": model}
        call_action(
            "issues_ticket_update",
            context=context,
            id=ticket["id"],
            status=Ticket.Status.closed,
        )

        # Try to add a message
        with pytest.raises(tk.ValidationError, match="Cannot add messages to closed tickets"):
            call_action(
                "issues_message_create",
                ticket_id=ticket["id"],
                author_id=user["id"],
                content="This should fail",
            )

    def test_create_message_on_nonexistent_ticket(self, user):
        """Test creating a message on a non-existent ticket."""
        with pytest.raises(tk.ValidationError, match="Ticket not found"):
            call_action(
                "issues_message_create",
                ticket_id="999999",
                author_id=user["id"],
                content="This should fail",
            )


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageDelete:
    @pytest.mark.usefixtures("with_request_context")
    def test_delete_message_as_author(self, ticket, user, mail_server):
        """Test that a user can delete their own message."""
        # Create a message
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="Test message",
        )

        # Get the message ID
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        message_id = updated_ticket["messages"][0]["id"]

        # Delete the message as the author
        context = {
            "user": user["name"],
            "model": model,
            "auth_user_obj": model.User.get(user["id"]),
        }
        result = call_action(
            "issues_message_delete",
            context=context,
            id=message_id,
        )

        assert result is True

        # Verify the message is deleted
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        assert len(updated_ticket["messages"]) == 0

    @pytest.mark.usefixtures("with_request_context")
    def test_delete_message_as_sysadmin(self, ticket, user, sysadmin, mail_server):
        """Test that a sysadmin can delete any message."""
        # Create a message
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="Test message",
        )

        # Get the message ID
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        message_id = updated_ticket["messages"][0]["id"]

        # Delete the message as sysadmin
        context = {"user": sysadmin["name"], "model": model}
        result = call_action(
            "issues_message_delete",
            context=context,
            id=message_id,
        )

        assert result is True

    # NOTE: authorization is covered in test_auth.py — call_action forces
    # ignore_auth=True, so it cannot exercise the auth functions here.

    def test_delete_nonexistent_message(self, sysadmin):
        """Test deleting a non-existent message."""
        context = {"user": sysadmin["name"], "model": model}

        with pytest.raises(tk.ValidationError, match="Message not found"):
            call_action(
                "issues_message_delete",
                context=context,
                id="999999",
            )


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageUpdate:
    @pytest.mark.usefixtures("with_request_context")
    def test_update_message_as_author(self, ticket, user, mail_server):
        """Test that a user can update their own message."""
        # Create a message
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="Original content",
        )

        # Get the message ID
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        message_id = updated_ticket["messages"][0]["id"]

        # Update the message as the author
        context = {
            "user": user["name"],
            "model": model,
            "auth_user_obj": model.User.get(user["id"]),
        }
        result = call_action(
            "issues_message_update",
            context=context,
            id=message_id,
            content="Updated content",
        )

        assert result["content"] == "Updated content"

        # Verify the message is updated
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        assert updated_ticket["messages"][0]["content"] == "Updated content"
        assert updated_ticket["messages"][0]["updated_at"] != updated_ticket["messages"][0]["created_at"]

    @pytest.mark.usefixtures("with_request_context")
    def test_update_message_as_sysadmin(self, ticket, user, sysadmin, mail_server):
        """Test that a sysadmin can update any message."""
        # Create a message
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="Original content",
        )

        # Get the message ID
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        message_id = updated_ticket["messages"][0]["id"]

        # Update the message as sysadmin
        context = {"user": sysadmin["name"], "model": model}
        result = call_action(
            "issues_message_update",
            context=context,
            id=message_id,
            content="Updated by sysadmin",
        )

        assert result["content"] == "Updated by sysadmin"

        # Verify the message is updated
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        assert updated_ticket["messages"][0]["content"] == "Updated by sysadmin"

    # NOTE: authorization is covered in test_auth.py — call_action forces
    # ignore_auth=True, so it cannot exercise the auth functions here.

    def test_update_nonexistent_message(self, sysadmin):
        """Test updating a non-existent message."""
        context = {"user": sysadmin["name"], "model": model}

        with pytest.raises(tk.ValidationError, match="Message not found"):
            call_action(
                "issues_message_update",
                context=context,
                id="999999",
                content="This should fail",
            )
