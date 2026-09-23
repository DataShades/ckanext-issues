from __future__ import annotations

import pytest

import ckan.model as model
from ckan.tests import factories
from ckan.tests.helpers import call_action

from ckanext.issues.model import Ticket, get_active_sysadmins


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestAssigneeDeletion:
    def test_deleting_the_assignee_unassigns_the_ticket(self, ticket):
        assignee = factories.User()

        t = Ticket.get(ticket["id"])
        t.assignee_id = assignee["id"]
        model.Session.commit()

        model.Session.delete(model.User.get(assignee["id"]))
        model.Session.commit()
        model.Session.expire_all()

        t = Ticket.get(ticket["id"])
        assert t is not None, "ticket was deleted along with its assignee"
        assert t.assignee_id is None, "ticket should be unassigned, not orphaned"

    def test_deleting_the_author_still_removes_their_tickets(self, ticket):
        # The author cascade is intentional; lock it in so a change is deliberate.
        author_id = ticket["author"]["id"]

        model.Session.delete(model.User.get(author_id))
        model.Session.commit()
        model.Session.expire_all()

        assert Ticket.get(ticket["id"]) is None


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestMessageAuthorDeletion:
    def test_purging_a_replier_removes_their_messages_but_keeps_the_ticket(self, ticket):
        staff = factories.Sysadmin()
        call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=staff["id"],
            content="staff reply",
        )

        model.Session.delete(model.User.get(staff["id"]))
        model.Session.commit()
        model.Session.expire_all()

        t = Ticket.get(ticket["id"])
        assert t is not None
        assert t.messages == []


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestActiveSysadmins:
    def test_only_active_sysadmins_ordered_by_name(self):
        b = factories.Sysadmin(name="b-admin")
        a = factories.Sysadmin(name="a-admin")
        deleted = factories.Sysadmin(name="c-admin")
        regular = factories.User(name="regular")
        call_action("user_delete", id=deleted["id"])

        # The site user is an active sysadmin too, so don't assert an exact list.
        names = [u.name for u in get_active_sysadmins()]
        assert names == sorted(names)
        assert {a["name"], b["name"]} <= set(names)
        assert deleted["name"] not in names
        assert regular["name"] not in names
