from __future__ import annotations

import pytest

import ckan.model as model
from ckan.tests import factories

from ckanext.issues.model import Ticket


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
