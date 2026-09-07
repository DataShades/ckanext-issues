from __future__ import annotations

import pytest
from sqlalchemy import select

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests.helpers import call_action

from ckanext.issues.model import Ticket

pytestmark = pytest.mark.usefixtures("with_plugins", "clean_db")

HX = {"HX-Request": "true"}


def _auth(user_id, extra=None):
    """Request headers that authenticate as ``user_id``.

    Uses an API token rather than ``CKANTestApp.set_session_user``, which only
    exists on newer CKAN versions.
    """
    token = call_action("api_token_create", user=user_id, name="pytest")["token"]
    headers = {"Authorization": token}
    if extra:
        headers = {**headers, **extra}
    return headers


def _assign(ticket_id, user_id):
    ticket = Ticket.get(ticket_id)
    ticket.assignee_id = user_id
    model.Session.commit()


def _add_message(ticket_id, author_id, content="original"):
    return call_action(
        "issues_message_create",
        ticket_id=ticket_id,
        author_id=author_id,
        content=content,
    )


def _messages(ticket_id):
    return call_action("issues_ticket_show", id=ticket_id)["messages"]


class TestTicketReadView:
    def test_author_can_open_the_ticket(self, app, ticket):
        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200
        assert f"#{ticket['id']}" in resp.body

    def test_assignee_can_open_the_ticket(self, app, ticket, user):
        _assign(ticket["id"], user["id"])

        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(user["id"]),
        )

        assert resp.status_code == 200

    def test_unrelated_user_is_forbidden(self, app, ticket, user):
        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(user["id"]),
        )

        assert resp.status_code == 403

    def test_anonymous_is_forbidden(self, app, ticket):
        resp = app.get(tk.url_for("issues.ticket_read", ticket_id=ticket["id"]))

        assert resp.status_code == 403

    def test_missing_ticket_is_404(self, app, ticket):
        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=999999),
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 404

    def test_non_numeric_ticket_id_is_404_not_500(self, app, ticket):
        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id="not-a-number"),
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 404

    def test_open_empty_thread_shows_the_no_replies_prompt(self, app, ticket):
        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(ticket["author"]["id"]),
        )

        assert "No replies yet" in resp.body

    def test_closed_empty_thread_hides_the_no_replies_prompt(self, app, ticket, sysadmin):
        call_action(
            "issues_ticket_update",
            context={"user": sysadmin["name"]},
            id=ticket["id"],
            status="closed",
        )

        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(ticket["author"]["id"]),
        )

        assert "No replies yet" not in resp.body


class TestAddMessageView:
    def test_author_can_reply(self, app, ticket):
        resp = app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "a reply"},
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200
        assert _messages(ticket["id"])[-1]["content"] == "a reply"

    def test_assignee_can_reply(self, app, ticket, user):
        _assign(ticket["id"], user["id"])

        app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "staff reply"},
            headers=_auth(user["id"]),
        )

        assert _messages(ticket["id"])[-1]["content"] == "staff reply"

    def test_unrelated_user_cannot_reply(self, app, ticket, user):
        app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "spam"},
            headers=_auth(user["id"]),
        )

        assert _messages(ticket["id"]) == []

    def test_cannot_reply_to_a_closed_ticket(self, app, ticket, sysadmin):
        call_action(
            "issues_ticket_update",
            context={"user": sysadmin["name"]},
            id=ticket["id"],
            status="closed",
        )

        app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "too late"},
            headers=_auth(ticket["author"]["id"]),
        )

        assert _messages(ticket["id"]) == []


class TestMessageMutation:
    def test_author_can_edit_own_message(self, app, ticket):
        message = _add_message(ticket["id"], ticket["author"]["id"])

        resp = app.post(
            tk.url_for("issues.update_message", message_id=message["id"]),
            data={"content": "edited"},
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200
        assert _messages(ticket["id"])[0]["content"] == "edited"

    def test_unrelated_user_cannot_edit_message(self, app, ticket, user):
        message = _add_message(ticket["id"], ticket["author"]["id"])

        app.post(
            tk.url_for("issues.update_message", message_id=message["id"]),
            data={"content": "hacked"},
            headers=_auth(user["id"]),
        )

        assert _messages(ticket["id"])[0]["content"] == "original"

    def test_non_numeric_message_id_does_not_500(self, app, ticket):
        resp = app.post(
            tk.url_for("issues.update_message", message_id="not-a-number"),
            data={"content": "x"},
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code < 500

    def test_author_can_delete_own_message(self, app, ticket):
        message = _add_message(ticket["id"], ticket["author"]["id"])

        resp = app.post(
            tk.url_for("issues.delete_message", message_id=message["id"]),
            data={"ticket_id": ticket["id"]},
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200
        assert _messages(ticket["id"]) == []
        # the re-rendered thread drops back to the empty state
        assert "No replies yet" in resp.body

    def test_deleting_one_of_several_messages_keeps_the_rest(self, app, ticket):
        _add_message(ticket["id"], ticket["author"]["id"], content="first")
        second = _add_message(ticket["id"], ticket["author"]["id"], content="second")

        resp = app.post(
            tk.url_for("issues.delete_message", message_id=second["id"]),
            data={"ticket_id": ticket["id"]},
            headers=_auth(ticket["author"]["id"]),
        )

        assert [m["content"] for m in _messages(ticket["id"])] == ["first"]
        assert "first" in resp.body
        assert "No replies yet" not in resp.body

    def test_unrelated_user_cannot_delete_message(self, app, ticket, user):
        message = _add_message(ticket["id"], ticket["author"]["id"])

        app.post(
            tk.url_for("issues.delete_message", message_id=message["id"]),
            data={"ticket_id": ticket["id"]},
            headers=_auth(user["id"]),
        )

        assert len(_messages(ticket["id"])) == 1


class TestTicketCreationAndModal:
    def test_authenticated_user_can_create_a_ticket(self, app, user):
        resp = app.post(
            tk.url_for("issues.add_ticket"),
            data={"subject": "Help", "category": "Data request", "text": "please"},
            headers=_auth(user["id"]),
        )

        assert resp.status_code == 200
        tickets = model.Session.scalars(select(Ticket).where(Ticket.author_id == user["id"])).all()
        assert len(tickets) == 1

    def test_init_modal_requires_authentication(self, app):
        resp = app.get(tk.url_for("issues.init_modal"))

        assert resp.status_code == 403

    def test_init_modal_renders_for_authenticated_user(self, app, user):
        resp = app.get(tk.url_for("issues.init_modal"), headers=_auth(user["id"]))

        assert resp.status_code == 200

    def test_my_tickets_page_renders(self, app, ticket):
        resp = app.get(
            tk.url_for("issues.my_tickets"),
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200


class TestAdminBlueprint:
    def test_sysadmin_sees_the_dashboard(self, app, sysadmin):
        resp = app.get(tk.url_for("issues_admin.list"), headers=_auth(sysadmin["id"]))

        assert resp.status_code == 200

    def test_regular_user_is_forbidden(self, app, user):
        resp = app.get(tk.url_for("issues_admin.list"), headers=_auth(user["id"]))

        assert resp.status_code == 403

    def test_anonymous_is_forbidden(self, app):
        resp = app.get(tk.url_for("issues_admin.list"))

        assert resp.status_code == 403

    def test_sysadmin_can_toggle_status(self, app, ticket, sysadmin):
        resp = app.post(
            tk.url_for("issues_admin.ticket_update_status", ticket_id=ticket["id"]),
            headers=_auth(sysadmin["id"], HX),
        )

        assert resp.status_code == 200
        assert call_action("issues_ticket_show", id=ticket["id"])["status"] == "closed"

    def test_sysadmin_can_assign_a_ticket(self, app, ticket, sysadmin, user):
        resp = app.post(
            tk.url_for("issues_admin.ticket_assign", ticket_id=ticket["id"]),
            data={"assignee_id": user["id"]},
            headers=_auth(sysadmin["id"], HX),
        )

        assert resp.status_code == 200
        assert call_action("issues_ticket_show", id=ticket["id"])["assignee"]["id"] == user["id"]

    def test_regular_user_cannot_toggle_status(self, app, ticket, user):
        resp = app.post(
            tk.url_for("issues_admin.ticket_update_status", ticket_id=ticket["id"]),
            headers=_auth(user["id"], HX),
        )

        assert resp.status_code == 403
        assert call_action("issues_ticket_show", id=ticket["id"])["status"] == "opened"

    def test_sysadmin_can_delete_a_ticket(self, app, ticket, sysadmin):
        resp = app.post(
            tk.url_for("issues_admin.ticket_delete", ticket_id=ticket["id"]),
            headers=_auth(sysadmin["id"], HX),
        )

        assert resp.status_code == 200
        with pytest.raises(tk.ValidationError, match="Ticket not found"):
            call_action("issues_ticket_show", id=ticket["id"])
