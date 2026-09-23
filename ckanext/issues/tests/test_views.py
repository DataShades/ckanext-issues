from __future__ import annotations

import pytest
from sqlalchemy import select

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests.helpers import call_action

from ckanext.issues.model import Ticket
from ckanext.issues.table import SupportTable

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

    def test_demoted_assignee_is_forbidden(self, app, ticket, user):
        _assign(ticket["id"], user["id"])

        resp = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(user["id"]),
        )

        assert resp.status_code == 403

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

    def test_successful_reply_tells_the_client_to_clear_the_form(self, app, ticket):
        resp = app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "a reply"},
            headers=_auth(ticket["author"]["id"], HX),
        )

        assert resp.headers.get("HX-Trigger") == "issues:message-added"

    def test_failed_reply_shows_the_error_inside_the_form(self, app, ticket):
        resp = app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": ""},
            headers=_auth(ticket["author"]["id"], HX),
        )

        assert "HX-Trigger" not in resp.headers
        assert resp.headers.get("HX-Retarget") == "#reply-form-errors"
        assert resp.headers.get("HX-Reswap") == "innerHTML"
        assert "Missing value" in resp.body
        assert "messages-container-outer" not in resp.body

    def test_sysadmin_can_reply(self, app, ticket, sysadmin):
        app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "staff reply"},
            headers=_auth(sysadmin["id"]),
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
            headers=_auth(ticket["author"]["id"]),
        )

        assert [m["content"] for m in _messages(ticket["id"])] == ["first"]
        assert "first" in resp.body
        assert "No replies yet" not in resp.body

    def test_unrelated_user_cannot_delete_message(self, app, ticket, user):
        message = _add_message(ticket["id"], ticket["author"]["id"])

        app.post(
            tk.url_for("issues.delete_message", message_id=message["id"]),
            headers=_auth(user["id"]),
        )

        assert len(_messages(ticket["id"])) == 1

    def test_delete_rerenders_own_thread_not_the_requested_one(self, app, ticket, ticket_factory, user):
        # A client-supplied ticket_id must not expose another ticket's thread.
        _add_message(ticket["id"], ticket["author"]["id"], content="private reply")
        own_ticket = ticket_factory(author_id=user["id"])
        message = _add_message(own_ticket["id"], user["id"])

        resp = app.post(
            tk.url_for("issues.delete_message", message_id=message["id"]),
            data={"ticket_id": ticket["id"]},
            headers=_auth(user["id"]),
        )

        assert resp.status_code == 200
        assert "private reply" not in resp.body
        assert "No replies yet" in resp.body


class TestTicketDeleteApi:
    def test_ticket_delete_is_not_callable_via_get(self, app, ticket, sysadmin):
        resp = app.get(
            "/api/action/issues_ticket_delete",
            query_string={"id": ticket["id"]},
            headers=_auth(sysadmin["id"]),
        )

        assert resp.status_code != 200
        assert call_action("issues_ticket_show", id=ticket["id"])


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

    def test_pages_set_the_browser_title(self, app, ticket, sysadmin):
        author = _auth(ticket["author"]["id"])

        my_tickets = app.get(tk.url_for("issues.my_tickets"), headers=author).body
        ticket_page = app.get(tk.url_for("issues.ticket_read", ticket_id=ticket["id"]), headers=author).body
        admin_list = app.get(tk.url_for("issues_admin.list"), headers=_auth(sysadmin["id"])).body

        assert "<title>My tickets" in my_tickets
        assert f"<title>{ticket['subject']}" in ticket_page
        assert f"Ticket #{ticket['id']}" in ticket_page
        assert "<title>Support tickets" in admin_list

    def test_my_tickets_has_a_heading_and_new_ticket_button(self, app, user):
        body = app.get(tk.url_for("issues.my_tickets"), headers=_auth(user["id"])).body

        assert ">My tickets</h1>" in body
        assert "New ticket" in body

    def test_my_tickets_page_renders(self, app, ticket):
        resp = app.get(
            tk.url_for("issues.my_tickets"),
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200


XHR = {"X-Requested-With": "XMLHttpRequest"}


def _table_rows(app, endpoint, user_id):
    resp = app.get(tk.url_for(endpoint), headers=_auth(user_id, XHR))
    assert resp.status_code == 200
    return {row["id"]: row for row in resp.json["data"]}


class TestTableContent:
    def test_my_tickets_lists_only_own_tickets(self, app, ticket_factory, user):
        own = ticket_factory(author_id=user["id"])
        other = ticket_factory()

        rows = _table_rows(app, "issues.my_tickets", user["id"])

        assert own["id"] in rows
        assert other["id"] not in rows

    def test_admin_list_shows_all_tickets_with_author_names(self, app, ticket_factory, sysadmin):
        first = ticket_factory()
        second = ticket_factory()

        rows = _table_rows(app, "issues_admin.list", sysadmin["id"])

        assert {first["id"], second["id"]} <= set(rows)
        assert first["author"]["name"] in rows[first["id"]]["author_name"]

    def test_admin_list_formats_status_and_user_links(self, app, ticket, sysadmin):
        call_action("issues_ticket_assign", id=ticket["id"], assignee_id=sysadmin["id"])

        row = _table_rows(app, "issues_admin.list", sysadmin["id"])[ticket["id"]]

        assert 'class="badge bg-success text-white">Open<' in row["status"]
        assert tk.url_for("user.read", id=ticket["author"]["name"]) in row["author_name"]
        assert tk.url_for("user.read", id=sysadmin["name"]) in row["assignee_name"]

    def test_admin_list_unassigned_ticket_has_empty_assignee(self, app, ticket, sysadmin):
        row = _table_rows(app, "issues_admin.list", sysadmin["id"])[ticket["id"]]

        assert not row["assignee_name"]

    @pytest.mark.parametrize("endpoint", ["issues_admin.list", "issues.my_tickets"])
    def test_subject_links_to_the_ticket(self, app, ticket, sysadmin, endpoint):
        user_id = sysadmin["id"] if endpoint == "issues_admin.list" else ticket["author"]["id"]
        row = _table_rows(app, endpoint, user_id)[ticket["id"]]

        assert tk.url_for("issues.ticket_read", ticket_id=ticket["id"]) in row["subject"]
        assert ticket["subject"] in row["subject"]

    def test_dates_use_the_display_timezone(self, app, ticket, sysadmin):
        row = _table_rows(app, "issues_admin.list", sysadmin["id"])[ticket["id"]]

        expected = tk.h.render_datetime(ticket["created_at"], date_format="%Y-%m-%d %H:%M")
        assert row["created_at"] == expected


class TestMissingTickets:
    def test_deleting_a_missing_ticket_redirects_with_an_error(self, app, sysadmin):
        resp = app.post(
            tk.url_for("issues_admin.ticket_delete", ticket_id=999999),
            headers=_auth(sysadmin["id"], HX),
        )

        assert resp.status_code == 200
        assert resp.headers.get("HX-Redirect") == tk.url_for("issues_admin.list")

    @pytest.mark.usefixtures("with_request_context")
    @pytest.mark.parametrize("bulk", ["bulk_close", "bulk_reopen", "bulk_delete"])
    def test_bulk_actions_skip_missing_tickets(self, bulk, ticket):
        rows = [{"id": 999999}, {"id": ticket["id"]}]

        result = getattr(SupportTable(), bulk)(rows)

        assert result["success"] is False
        assert "999999" in result["error"]
        # the existing ticket was still processed
        if bulk == "bulk_delete":
            assert Ticket.get(ticket["id"]) is None
        elif bulk == "bulk_close":
            assert Ticket.get(ticket["id"]).status == Ticket.Status.closed


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

    def test_sysadmin_can_assign_a_ticket(self, app, ticket, sysadmin):
        resp = app.post(
            tk.url_for("issues_admin.ticket_assign", ticket_id=ticket["id"]),
            data={"assignee_id": sysadmin["id"]},
            headers=_auth(sysadmin["id"], HX),
        )

        assert resp.status_code == 200
        assert call_action("issues_ticket_show", id=ticket["id"])["assignee"]["id"] == sysadmin["id"]

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


class TestHeader:
    """The account-nav additions from ``templates/header.html``."""

    def test_anonymous_does_not_see_the_support_trigger(self, app):
        body = app.get(tk.url_for("home.index")).body

        assert tk.url_for("issues.init_modal") not in body
        assert tk.url_for("issues.my_tickets") not in body

    def test_regular_user_sees_the_support_trigger(self, app, user):
        body = app.get(tk.url_for("home.index"), headers=_auth(user["id"])).body

        assert tk.url_for("issues.init_modal") in body
        assert tk.url_for("issues.my_tickets") in body
        assert tk.url_for("issues_admin.list") not in body

    def test_sysadmin_sees_the_admin_link(self, app, sysadmin):
        body = app.get(tk.url_for("home.index"), headers=_auth(sysadmin["id"])).body

        assert tk.url_for("issues.init_modal") in body
        assert tk.url_for("issues_admin.list") in body


class TestFrontend:
    def test_modal_is_not_injected_for_anonymous(self, app):
        body = app.get(tk.url_for("home.index")).body

        assert 'id="issues-ticket-modal"' not in body

    def test_modal_is_injected_for_authenticated_user(self, app, user):
        body = app.get(tk.url_for("home.index"), headers=_auth(user["id"])).body

        assert 'id="issues-ticket-modal"' in body

    def test_htmx_controls_disable_themselves_while_pending(self, app, ticket, sysadmin):
        _add_message(ticket["id"], sysadmin["id"])

        modal = app.get(tk.url_for("issues.init_modal"), headers=_auth(sysadmin["id"])).body
        page = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(sysadmin["id"]),
        ).body

        assert "hx-disabled-elt" in modal
        # reply, assign, close, delete ticket, message delete + edit
        assert page.count("hx-disabled-elt") == 6

    def test_edit_controls_only_on_own_messages(self, app, ticket, sysadmin):
        own = _add_message(ticket["id"], ticket["author"]["id"])
        other = _add_message(ticket["id"], sysadmin["id"])

        body = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(ticket["author"]["id"]),
        ).body

        assert f'data-issues-toggle-edit="{own["id"]}"' in body
        assert f'data-issues-toggle-edit="{other["id"]}"' not in body
        assert "toggleMsgEdit" not in body

    def test_closed_ticket_has_no_edit_controls_and_no_reopen_hint(self, app, ticket):
        message = _add_message(ticket["id"], ticket["author"]["id"])
        call_action("issues_ticket_update", id=ticket["id"], status="closed")

        body = app.get(
            tk.url_for("issues.ticket_read", ticket_id=ticket["id"]),
            headers=_auth(ticket["author"]["id"]),
        ).body

        assert f'data-issues-toggle-edit="{message["id"]}"' not in body
        assert "Reopen the ticket" not in body
        assert "Open a new ticket" in body

    def test_create_errors_are_readable(self, app, user):
        resp = app.post(
            tk.url_for("issues.add_ticket"),
            data={"subject": "Help", "category": "no-such-category", "text": "please"},
            headers=_auth(user["id"]),
        )

        assert "is not allowed" in resp.body
        assert "{&#39;" not in resp.body

    def test_create_error_keeps_the_submitted_values(self, app, user):
        resp = app.post(
            tk.url_for("issues.add_ticket"),
            data={"subject": "Keep me", "category": "no-such-category", "text": "my long draft"},
            headers=_auth(user["id"]),
        )

        assert 'id="add-ticket-form"' in resp.body
        assert 'value="Keep me"' in resp.body
        assert "my long draft" in resp.body

    @pytest.mark.ckan_config("ckanext.issues.max_open_tickets_per_user", "1")
    def test_open_ticket_limit_is_shown_above_the_form(self, app, user):
        data = {"subject": "Help", "category": "Data request", "text": "please"}
        app.post(tk.url_for("issues.add_ticket"), data=data, headers=_auth(user["id"]))

        resp = app.post(tk.url_for("issues.add_ticket"), data=data, headers=_auth(user["id"]))

        assert 'class="alert alert-danger"' in resp.body
        assert "open support tickets" in resp.body
        assert 'value="Help"' in resp.body

    def test_create_success_links_to_the_ticket(self, app, user):
        resp = app.post(
            tk.url_for("issues.add_ticket"),
            data={"subject": "Help", "category": "Data request", "text": "please"},
            headers=_auth(user["id"]),
        )

        ticket = model.Session.scalars(select(Ticket).where(Ticket.author_id == user["id"])).one()
        assert tk.url_for("issues.ticket_read", ticket_id=ticket.id) in resp.body
        assert tk.url_for("issues.my_tickets") in resp.body

    def test_htmx_error_triggers_a_refresh(self, app, ticket, user):
        message = _add_message(ticket["id"], ticket["author"]["id"])

        resp = app.post(
            tk.url_for("issues.delete_message", message_id=message["id"]),
            headers=_auth(user["id"], HX),
        )

        assert resp.status_code == 200
        assert resp.headers.get("HX-Refresh") == "true"
        assert len(_messages(ticket["id"])) == 1
