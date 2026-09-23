from __future__ import annotations

import pytest

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests import factories
from ckan.tests.helpers import call_action, call_auth

from ckanext.issues.model import Ticket


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTicketAuth:
    """Test authorization for ticket operations."""

    def test_ticket_create_anon(self):
        """Test that anonymous users cannot create tickets."""
        with pytest.raises(tk.NotAuthorized):
            call_auth("issues_ticket_create", context={"user": None, "model": model})

    def test_ticket_create_regular_user(self, user):
        """Test that regular users can create tickets."""
        result = call_auth("issues_ticket_create", context={"user": user["name"], "model": model})
        assert result is True

    def test_ticket_create_on_behalf_of_another_user(self, user):
        other_user = factories.User()
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_ticket_create",
                context={"user": user["name"], "model": model},
                author_id=other_user["id"],
            )

    def test_ticket_create_as_self(self, user):
        result = call_auth(
            "issues_ticket_create",
            context={"user": user["name"], "model": model},
            author_id=user["id"],
        )
        assert result is True

    def test_ticket_delete_anon(self):
        """Test that anonymous users cannot delete tickets."""
        with pytest.raises(tk.NotAuthorized):
            call_auth("issues_ticket_delete", context={"user": None, "model": model})

    def test_ticket_delete_regular_user(self, user):
        """Test that regular users cannot delete tickets."""
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_ticket_delete",
                context={"user": user["name"], "model": model},
            )

    def test_ticket_delete_sysadmin(self, sysadmin):
        """Test that sysadmins can delete tickets."""
        result = call_auth(
            "issues_ticket_delete",
            context={"user": sysadmin["name"], "model": model},
        )
        assert result is True


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageAuth:
    """Test authorization for message operations."""

    def test_message_delete_anon(self):
        """Test that anonymous users cannot delete messages."""
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_delete",
                context={"user": None, "model": model},
                data_dict={"id": "1"},
            )

    def test_message_delete_own_message(self, ticket, user):
        """Test that users can delete their own messages."""
        from ckan.tests.helpers import call_action

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

        # Check auth for deleting own message
        user_obj = model.User.get(user["id"])
        result = call_auth(
            "issues_message_delete",
            context={"user": user["name"], "model": model, "auth_user_obj": user_obj},
            id=message_id,
        )
        assert result is True

    def test_message_delete_others_message(self, ticket, user):
        """Test that users cannot delete others' messages."""
        from ckan.tests.helpers import call_action

        # Create a message with a different user
        other_user = factories.User()
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=other_user["id"],
            content="Test message",
        )

        # Get the message ID
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        message_id = updated_ticket["messages"][0]["id"]

        # Check auth for deleting others' message
        user_obj = model.User.get(user["id"])
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_delete",
                context={"user": user["name"], "model": model, "auth_user_obj": user_obj},
                id=message_id,
            )

    def test_message_delete_sysadmin(self, ticket, user, sysadmin):
        """Test that sysadmins can delete any message."""
        from ckan.tests.helpers import call_action

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

        # Check auth for sysadmin
        result = call_auth(
            "issues_message_delete",
            context={"user": sysadmin["name"], "model": model},
            data_dict={"id": message_id},
        )
        assert result is True

    def test_message_update_anon(self):
        """Test that anonymous users cannot update messages."""
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_update",
                context={"user": None, "model": model},
                data_dict={"id": "1"},
            )

    def test_message_update_own_message(self, ticket, user):
        """Test that users can update their own messages."""
        from ckan.tests.helpers import call_action

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

        # Check auth for updating own message
        user_obj = model.User.get(user["id"])
        result = call_auth(
            "issues_message_update",
            context={"user": user["name"], "model": model, "auth_user_obj": user_obj},
            id=message_id,
        )
        assert result is True

    def test_message_update_others_message(self, ticket, user):
        """Test that users cannot update others' messages."""
        from ckan.tests.helpers import call_action

        # Create a message with a different user
        other_user = factories.User()
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=other_user["id"],
            content="Test message",
        )

        # Get the message ID
        updated_ticket = call_action("issues_ticket_show", id=ticket["id"])
        message_id = updated_ticket["messages"][0]["id"]

        # Check auth for updating others' message
        user_obj = model.User.get(user["id"])
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_update",
                context={"user": user["name"], "model": model, "auth_user_obj": user_obj},
                id=message_id,
            )

    def test_message_update_sysadmin(self, ticket, user, sysadmin):
        """Test that sysadmins can update any message."""
        from ckan.tests.helpers import call_action

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

        # Check auth for sysadmin
        result = call_auth(
            "issues_message_update",
            context={"user": sysadmin["name"], "model": model},
            data_dict={"id": message_id},
        )
        assert result is True


def _assign(ticket_id, user_id):
    """Assign a ticket at the model level (the assign action is sysadmin-only)."""
    t = Ticket.get(ticket_id)
    t.assignee_id = user_id
    model.Session.commit()


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestTicketShowAuth:
    """The ticket author may view it (sysadmins, incl. assignees, via core)."""

    def test_author_can_view(self, ticket):
        result = call_auth(
            "issues_ticket_show",
            context={"user": ticket["author"]["name"], "model": model},
            id=ticket["id"],
        )
        assert result is True

    def test_demoted_assignee_cannot_view(self, ticket, user):
        # Assignees get access only through the sysadmin flag.
        _assign(ticket["id"], user["id"])
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_ticket_show",
                context={"user": user["name"], "model": model},
                id=ticket["id"],
            )

    def test_unrelated_user_cannot_view(self, ticket, user):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_ticket_show",
                context={"user": user["name"], "model": model},
                id=ticket["id"],
            )

    def test_sysadmin_can_view(self, ticket, sysadmin):
        result = call_auth(
            "issues_ticket_show",
            context={"user": sysadmin["name"], "model": model},
            id=ticket["id"],
        )
        assert result is True

    def test_anon_cannot_view(self, ticket):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_ticket_show",
                context={"user": None, "model": model},
                id=ticket["id"],
            )


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageCreateAuth:
    """The ticket author may post messages (sysadmins via core)."""

    def test_message_create_by_author(self, ticket):
        result = call_auth(
            "issues_message_create",
            context={"user": ticket["author"]["name"], "model": model},
            ticket_id=ticket["id"],
        )
        assert result is True

    def test_message_create_by_demoted_assignee(self, ticket, user):
        _assign(ticket["id"], user["id"])
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_create",
                context={"user": user["name"], "model": model},
                ticket_id=ticket["id"],
            )

    def test_message_create_as_another_user(self, ticket, sysadmin):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_create",
                context={"user": ticket["author"]["name"], "model": model},
                ticket_id=ticket["id"],
                author_id=sysadmin["id"],
            )

    def test_message_create_by_other_user(self, ticket, user):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_create",
                context={"user": user["name"], "model": model},
                ticket_id=ticket["id"],
            )

    def test_message_create_by_sysadmin(self, ticket, sysadmin):
        result = call_auth(
            "issues_message_create",
            context={"user": sysadmin["name"], "model": model},
            ticket_id=ticket["id"],
        )
        assert result is True

    def test_message_create_anon(self, ticket):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "issues_message_create",
                context={"user": None, "model": model},
                ticket_id=ticket["id"],
            )


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageMutationOnClosedTicket:
    """Authors can't edit or delete their messages once the ticket is closed."""

    @pytest.mark.parametrize("action", ["issues_message_update", "issues_message_delete"])
    def test_denied_on_closed_ticket(self, action, ticket):
        message = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=ticket["author"]["id"],
            content="reply",
        )
        call_action("issues_ticket_update", id=ticket["id"], status=Ticket.Status.closed)

        with pytest.raises(tk.NotAuthorized):
            call_auth(
                action,
                context={"user": ticket["author"]["name"], "model": model},
                id=message["id"],
            )
