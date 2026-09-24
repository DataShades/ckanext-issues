from __future__ import annotations

from typing import TYPE_CHECKING, Any

from flask import Blueprint, Response
from flask.views import MethodView

import ckan.plugins.toolkit as tk
from ckan.logic import parse_params

from ckanext.tables.shared import GenericTableView

from ckanext.issues.model import TicketMessage
from ckanext.issues.table import SupportTable, UserTicketTable

if TYPE_CHECKING:
    from ckanext.issues.types import DictizedMessage, DictizedTicket

_TICKET_FORM_FIELDS = ("subject", "category", "text")

issues = Blueprint(
    "issues",
    __name__,
    url_prefix="/issues",
)

issues_admin = Blueprint(
    "issues_admin",
    __name__,
    url_prefix="/issues/admin",
)


def _sysadmin_before_request() -> None:
    try:
        tk.check_access("sysadmin", {"user": tk.current_user.name})
    except tk.NotAuthorized:
        tk.abort(403, tk._("Need to be system administrator to administer"))


def _authenticated_before_request() -> None:
    if not tk.current_user.is_authenticated:
        tk.abort(403, tk._("You must be logged in to access this page"))


def _error_message(error: Exception) -> str:
    """Human-readable text for an action error."""
    if isinstance(error, tk.ValidationError):
        return "; ".join(f"{field}: {msg}" for field, msg in error.error_summary.items())

    if isinstance(error, tk.NotAuthorized):
        return str(error) or tk._("You are not allowed to do this")

    return str(error)


def _error_response(error: Exception) -> Response:
    """Flash the error and make sure the user actually sees it.

    htmx doesn't swap 4xx responses, so for htmx requests reply 200 with
    ``HX-Refresh`` and let the reloaded page render the flash.
    """
    tk.h.flash_error(_error_message(error))

    if tk.request.headers.get("HX-Request"):
        return Response("", status=200, headers={"HX-Refresh": "true"})

    return Response("", status=400)


issues_admin.before_request(_sysadmin_before_request)
issues.before_request(_authenticated_before_request)


def init_modal() -> str:
    """This view inits the modal data on first open or after a submit."""
    return tk.render("issues/ticket_modal_form.html")


class AddTicketView(MethodView):
    def post(self) -> str:
        data_dict = parse_params(tk.request.form)
        data_dict["author_id"] = tk.g.userobj.id

        try:
            ticket: DictizedTicket = tk.get_action("issues_ticket_create")({"user": tk.g.user}, data_dict)
        except (tk.ObjectNotFound, tk.ValidationError) as e:
            return self._render_form(data_dict, e)

        return tk.render(
            "issues/ticket_modal_response.html",
            extra_vars={
                "title": tk._("Your ticket has been successfully created"),
                "message": tk._("We will get back to you as soon as possible."),
                "ticket": ticket,
            },
        )

    def _render_form(self, data: dict[str, Any], error: Exception) -> str:
        """Re-render the form with the submitted values and inline errors."""
        errors: dict[str, Any] = {}
        form_errors: list[str] = []

        if isinstance(error, tk.ValidationError):
            for field, messages in error.error_dict.items():
                if field in _TICKET_FORM_FIELDS:
                    errors[field] = messages
                else:
                    form_errors.extend(messages if isinstance(messages, list) else [str(messages)])
        else:
            form_errors.append(_error_message(error))

        return tk.render(
            "issues/ticket_modal_form.html",
            extra_vars={
                "data": data,
                "errors": errors,
                "form_error": " ".join(form_errors),
            },
        )


class AddMessageView(MethodView):
    def post(self, ticket_id: str) -> Response | str:
        data_dict = parse_params(tk.request.form)

        try:
            message: DictizedMessage = tk.get_action("issues_message_create")(
                {"user": tk.g.user},
                {
                    "ticket_id": ticket_id,
                    "author_id": tk.current_user.id,
                    "content": data_dict.get("content", ""),
                },
            )
        except (tk.ObjectNotFound, tk.ValidationError, tk.NotAuthorized) as e:
            # Show the error inside the reply form instead of swapping it over
            # the thread.
            return Response(
                tk.render("issues/reply_form_error.html", extra_vars={"message": _error_message(e)}),
                headers={"HX-Retarget": "#reply-form-errors", "HX-Reswap": "innerHTML"},
            )

        ticket: DictizedTicket = tk.get_action("issues_ticket_show")(
            {"ignore_auth": True},
            {"id": ticket_id},
        )

        # The reply form lives outside the swapped thread; tell the client to
        # clear it and move to the new message once it is in the DOM. Only
        # sent on success, so a failed post keeps the draft.
        return Response(
            tk.render(
                "issues/messages_container.html",
                extra_vars={"ticket": ticket, "new_message_id": message["id"]},
            ),
            headers={"HX-Trigger-After-Settle": "issues:message-added"},
        )


class DeleteMessageView(MethodView):
    def post(self, message_id: str) -> Response | str:
        message = TicketMessage.get(message_id)
        ticket_id = message.ticket_id if message else None

        try:
            tk.get_action("issues_message_delete")(
                {"user": tk.g.user},
                {"id": message_id},
            )
        except (tk.ObjectNotFound, tk.ValidationError, tk.NotAuthorized) as e:
            return _error_response(e)

        # Re-render the whole thread so the reply counter and the empty state
        # stay in sync.
        ticket: DictizedTicket = tk.get_action("issues_ticket_show")(
            {"ignore_auth": True},
            {"id": ticket_id},
        )

        return tk.render(
            "issues/messages_container.html",
            extra_vars={"ticket": ticket},
        )


class UpdateMessageView(MethodView):
    def post(self, message_id: str) -> str:
        data_dict = parse_params(tk.request.form)
        data_dict["id"] = message_id

        try:
            message: DictizedMessage = tk.get_action("issues_message_update")(
                {"user": tk.g.user},
                data_dict,
            )
        except (tk.ObjectNotFound, tk.ValidationError, tk.NotAuthorized) as e:
            return tk.render(
                "issues/ticket_modal_response.html",
                extra_vars={
                    "title": tk._("Error updating message"),
                    "message": _error_message(e),
                },
            )

        ticket: DictizedTicket = tk.get_action("issues_ticket_show")(
            {"ignore_auth": True},
            {"id": message["ticket_id"]},
        )

        return tk.render(
            "issues/message_item.html",
            extra_vars={"message": message, "ticket": ticket},
        )


class TicketReadView(MethodView):
    def get(self, ticket_id: str) -> str:
        # Authorization (author / sysadmin) lives in the issues_ticket_show
        # auth function.
        try:
            ticket: DictizedTicket = tk.get_action("issues_ticket_show")(
                {"user": tk.current_user.name},
                {"id": ticket_id},
            )
        except (tk.ObjectNotFound, tk.ValidationError):
            return tk.abort(404, tk._("Ticket not found"))
        except tk.NotAuthorized:
            return tk.abort(403, tk._("You are not allowed to view this ticket"))

        return tk.render("issues/ticket_read.html", extra_vars={"ticket": ticket})


class TicketUpdateStatusView(MethodView):
    def post(self, ticket_id: str) -> Response:
        try:
            ticket: DictizedTicket = tk.get_action("issues_ticket_show")(
                {"ignore_auth": True},
                {"id": ticket_id},
            )
            new_status = "closed" if ticket["status"] == "opened" else "opened"
            tk.get_action("issues_ticket_update")(
                {"user": tk.g.user},
                {"id": ticket_id, "status": new_status},
            )
        except (tk.ObjectNotFound, tk.ValidationError, tk.NotAuthorized) as e:
            return _error_response(e)

        redirect_url: str = tk.url_for("issues.ticket_read", ticket_id=ticket_id)

        if tk.request.headers.get("HX-Request"):
            return Response("", status=200, headers={"HX-Redirect": redirect_url})

        return tk.redirect_to(redirect_url)


class TicketAssignView(MethodView):
    def post(self, ticket_id: str) -> Response:
        data_dict = parse_params(tk.request.form)

        action_data: dict[str, Any] = {
            "id": ticket_id,
            "assignee_id": data_dict.get("assignee_id"),
        }

        try:
            tk.get_action("issues_ticket_assign")(
                {"user": tk.g.user},
                action_data,
            )
        except (tk.ObjectNotFound, tk.ValidationError, tk.NotAuthorized) as e:
            return _error_response(e)

        redirect_url: str = tk.url_for("issues.ticket_read", ticket_id=ticket_id)

        if tk.request.headers.get("HX-Request"):
            return Response("", status=200, headers={"HX-Redirect": redirect_url})

        return tk.redirect_to(redirect_url)


class TicketDeleteView(MethodView):
    def post(self, ticket_id: str) -> Response:
        try:
            tk.get_action("issues_ticket_delete")(
                {"user": tk.current_user.name},
                {"id": ticket_id},
            )
        except (tk.ObjectNotFound, tk.ValidationError, tk.NotAuthorized) as e:
            # The ticket page is gone (or never existed); go back to the list.
            tk.h.flash_error(_error_message(e))
        else:
            tk.h.flash_success(tk._("The ticket has been deleted"))

        redirect_url: str = tk.url_for("issues_admin.list")

        if tk.request.headers.get("HX-Request"):
            return Response("", status=200, headers={"HX-Redirect": redirect_url})

        return tk.redirect_to(redirect_url)


# issues — authenticated users
issues.add_url_rule(
    "/my-tickets",
    view_func=GenericTableView.as_view("my_tickets", table=UserTicketTable),
)
issues.add_url_rule("/ticket/<ticket_id>", view_func=TicketReadView.as_view("ticket_read"))
issues.add_url_rule("/ticket/<ticket_id>/message", view_func=AddMessageView.as_view("add_message"))
issues.add_url_rule("/init_modal", view_func=init_modal)
issues.add_url_rule("/add_ticket", view_func=AddTicketView.as_view("add_ticket"), methods=("POST",))
issues.add_url_rule(
    "/message/<message_id>/delete",
    view_func=DeleteMessageView.as_view("delete_message"),
    methods=("POST",),
)
issues.add_url_rule(
    "/message/<message_id>/update",
    view_func=UpdateMessageView.as_view("update_message"),
    methods=("POST",),
)
# issues_admin — sysadmins only
issues_admin.add_url_rule("/", view_func=GenericTableView.as_view("list", table=SupportTable))
issues_admin.add_url_rule(
    "/ticket/<ticket_id>/update-status",
    view_func=TicketUpdateStatusView.as_view("ticket_update_status"),
    methods=("POST",),
)
issues_admin.add_url_rule(
    "/ticket/<ticket_id>/assign",
    view_func=TicketAssignView.as_view("ticket_assign"),
    methods=("POST",),
)
issues_admin.add_url_rule(
    "/ticket/<ticket_id>/delete",
    view_func=TicketDeleteView.as_view("ticket_delete"),
    methods=("POST",),
)
