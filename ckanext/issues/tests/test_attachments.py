"""File attachments (optional ckanext-files integration)."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import pytest
import sqlalchemy as sa
from werkzeug.datastructures import FileStorage, Headers

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests import factories
from ckan.tests.helpers import call_action, call_auth

from ckanext.issues import attachments
from ckanext.issues import config as issues_config
from ckanext.issues.model import Ticket

pytestmark = pytest.mark.skipif(not attachments.installed(), reason="ckanext-files is not installed")

# 1x1 transparent PNG: big enough for content-type detection.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=",
)

# Storages are core on CKAN 2.12+ and come from ckanext-files before; set
# both, each version reads its own keys.
with_files = [
    pytest.mark.ckan_config("ckan.plugins", "tables issues files"),
    pytest.mark.ckan_config("ckanext.issues.attachments.storage", "issues_test"),
    pytest.mark.ckan_config("ckan.files.storage.issues_test.type", "ckan:memory"),
    pytest.mark.ckan_config("ckan.files.storage.issues_test.path", "/issues-test"),
    pytest.mark.ckan_config("ckanext.files.storage.issues_test.type", "files:redis"),
]


@pytest.fixture
def with_attachments(request: pytest.FixtureRequest, with_plugins: Any, clean_db: Any, migrate_db_for: Any):
    if tk.check_ckan_version("2.12"):
        # The storage type comes from the files plugin, loaded just now.
        request.getfixturevalue("reset_storages")()
    else:
        migrate_db_for("files")


def png(name: str = "shot.png") -> FileStorage:
    return FileStorage(BytesIO(PNG), filename=name)


def text(name: str = "notes.txt", content: bytes = b"hello world, plain text") -> FileStorage:
    return FileStorage(BytesIO(content), filename=name)


def _create_ticket(author_id: str, **extra: Any) -> dict[str, Any]:
    return call_action(
        "issues_ticket_create",
        subject="Preview issue",
        text="The map stays empty.",
        category="Data request",
        author_id=author_id,
        **extra,
    )


def _file_exists(file_id: str) -> bool:
    try:
        call_action("files_file_show", id=file_id)
    except tk.ObjectNotFound:
        return False
    return True


def _auth(user_id: str) -> dict[str, str]:
    token = call_action("api_token_create", user=user_id, name="pytest")["token"]
    return {"Authorization": token}


def _apply(marks: list[Any]):
    def decorator(obj: Any) -> Any:
        for mark in marks:
            obj = mark(obj)
        return obj

    return decorator


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestCreate:
    def test_ticket_keeps_its_files(self, user):
        ticket = _create_ticket(user["id"], attachments=[png(), text()])

        files = {f["name"]: f for f in ticket["attachments"]}
        assert set(files) == {"shot.png", "notes.txt"}
        assert files["shot.png"]["content_type"] == "image/png"
        assert files["shot.png"]["size"] == len(PNG)
        assert files["notes.txt"]["content_type"] == "text/plain"

        shown = call_action("issues_ticket_show", id=ticket["id"])
        assert [f["id"] for f in shown["attachments"]] == [f["id"] for f in ticket["attachments"]]

    def test_files_are_owned_and_pinned_by_the_ticket(self, user):
        ticket = _create_ticket(user["id"], attachments=[png()])

        info = call_action("files_file_show", id=ticket["attachments"][0]["id"])
        assert info["owner_type"] == attachments.OWNER_TICKET
        assert info["owner_id"] == str(ticket["id"])
        assert info["pinned"] is True

    def test_reply_keeps_its_files(self, ticket):
        message = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=ticket["author"]["id"],
            content="Here is a screenshot",
            attachments=[png()],
        )

        assert [f["name"] for f in message["attachments"]] == ["shot.png"]

        shown = call_action("issues_ticket_show", id=ticket["id"])
        assert shown["attachments"] == []
        assert [f["name"] for f in shown["messages"][0]["attachments"]] == ["shot.png"]

    def test_the_same_file_name_can_be_attached_twice(self, user):
        first = _create_ticket(user["id"], attachments=[png()])
        second = _create_ticket(user["id"], attachments=[png()])

        assert first["attachments"][0]["name"] == second["attachments"][0]["name"] == "shot.png"
        assert first["attachments"][0]["id"] != second["attachments"][0]["id"]

    def test_without_files_the_list_is_empty(self, user):
        ticket = _create_ticket(user["id"])

        assert ticket["attachments"] == []


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestLimits:
    @pytest.mark.ckan_config("ckanext.issues.attachments.max_files", 1)
    def test_too_many_files(self, user):
        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], attachments=[png("a.png"), png("b.png")])

        assert "attachments" in err.value.error_dict
        assert Ticket.count_open_for_author(user["id"]) == 0

    @pytest.mark.ckan_config("ckanext.issues.attachments.max_size", 10)
    def test_too_large(self, user):
        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], attachments=[png()])

        assert "shot.png" in err.value.error_dict["attachments"][0]
        assert Ticket.count_open_for_author(user["id"]) == 0

    @pytest.mark.ckan_config("ckanext.issues.attachments.max_size", 10)
    def test_size_is_measured_not_taken_from_the_request(self, user):
        # A multipart part may claim its own Content-Length.
        spoofed = FileStorage(BytesIO(PNG), filename="shot.png", headers=Headers({"Content-Length": "1"}))

        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], attachments=[spoofed])

        assert "shot.png" in err.value.error_dict["attachments"][0]

    def test_stored_size_is_the_real_size(self, user):
        spoofed = FileStorage(BytesIO(PNG), filename="shot.png", headers=Headers({"Content-Length": "1"}))

        ticket = _create_ticket(user["id"], attachments=[spoofed])

        assert ticket["attachments"][0]["size"] == len(PNG)

    @pytest.mark.ckan_config("ckanext.issues.attachments.allowed_types", "image/*")
    def test_type_is_detected_from_the_content(self, user):
        # Named like an image, but it's text.
        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], attachments=[text("fake.png")])

        assert "fake.png" in err.value.error_dict["attachments"][0]

    @pytest.mark.ckan_config("ckanext.issues.attachments.allowed_types", "image/*")
    def test_wildcard_type_allows_the_family(self, user):
        ticket = _create_ticket(user["id"], attachments=[png()])

        assert len(ticket["attachments"]) == 1

    @pytest.mark.ckan_config("ckanext.issues.attachments.max_files", 0)
    def test_zero_max_files_turns_uploads_off(self, user):
        with pytest.raises(tk.ValidationError):
            _create_ticket(user["id"], attachments=[png()])

    def test_failed_storage_creates_no_ticket(self, user, monkeypatch):
        def broken(*args: Any, **kwargs: Any):
            raise tk.ValidationError({"upload": ["storage is down"]})

        monkeypatch.setattr(attachments, "store", broken)

        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], attachments=[png()])

        assert "storage is down" in err.value.error_dict["attachments"][0]
        assert Ticket.count_open_for_author(user["id"]) == 0

    def test_failed_hand_over_removes_the_ticket_and_its_files(self, user, monkeypatch):
        stored: list[str] = []
        real_store = attachments.store

        def spy(*args: Any, **kwargs: Any) -> list[str]:
            stored.extend(real_store(*args, **kwargs))
            return stored

        def broken(*args: Any, **kwargs: Any):
            raise RuntimeError("transfer failed")

        monkeypatch.setattr(attachments, "store", spy)
        monkeypatch.setattr(attachments, "assign", broken)

        with pytest.raises(tk.ValidationError):
            _create_ticket(user["id"], attachments=[png()])

        assert Ticket.count_open_for_author(user["id"]) == 0
        assert stored
        assert not any(_file_exists(file_id) for file_id in stored)

    @pytest.mark.ckan_config("ckanext.issues.max_open_tickets_per_user", 1)
    def test_rejected_ticket_leaves_no_files(self, user, monkeypatch):
        stored: list[str] = []
        real_store = attachments.store

        def spy(*args: Any, **kwargs: Any) -> list[str]:
            stored.extend(real_store(*args, **kwargs))
            return stored

        monkeypatch.setattr(attachments, "store", spy)
        # The open-ticket limit doesn't apply to ignore_auth callers.
        as_user = {"user": user["name"], "ignore_auth": False}
        _create_ticket(user["id"], context=dict(as_user))

        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], context=dict(as_user), attachments=[png()])

        assert "author_id" in err.value.error_dict

        assert stored
        assert not any(_file_exists(file_id) for file_id in stored)


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestStorageChecks:
    def test_missing_storage_turns_uploads_off(self, user, monkeypatch):
        monkeypatch.setattr(issues_config, "get_attachments_storage", lambda: "not-configured")

        assert not attachments.uploads_allowed()
        with pytest.raises(tk.ValidationError):
            _create_ticket(user["id"], attachments=[png()])

    # A real bool: marks skip config normalisation, and core groups storages
    # by `settings.public` in a dict keyed by True/False.
    @pytest.mark.ckan_config("ckan.files.storage.issues_test.public", True)
    @pytest.mark.ckan_config("ckanext.files.storage.issues_test.public", True)
    def test_public_storage_turns_uploads_off(self, user):
        assert not attachments.uploads_allowed()
        with pytest.raises(tk.ValidationError):
            _create_ticket(user["id"], attachments=[png()])

    def test_private_storage_is_used(self):
        assert attachments.uploads_allowed()


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestDelete:
    def test_deleting_a_reply_deletes_its_files(self, ticket):
        message = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=ticket["author"]["id"],
            content="screenshot",
            attachments=[png()],
        )
        file_id = message["attachments"][0]["id"]

        call_action("issues_message_delete", id=message["id"])

        assert not _file_exists(file_id)

    def test_deleting_a_ticket_deletes_all_its_files(self, user):
        ticket = _create_ticket(user["id"], attachments=[png()])
        message = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="one more",
            attachments=[text()],
        )
        file_ids = [ticket["attachments"][0]["id"], message["attachments"][0]["id"]]

        call_action("issues_ticket_delete", id=ticket["id"])

        assert not any(_file_exists(file_id) for file_id in file_ids)


def _purge(user_id: str) -> None:
    model.Session.delete(model.User.get(user_id))
    model.Session.commit()
    model.Session.expire_all()


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestUserPurge:
    """Purging a user leaves their attachments for ``clean-attachments``."""

    def test_purging_the_author_orphans_the_files_of_their_tickets(self, user):
        staff = factories.Sysadmin()
        ticket = _create_ticket(user["id"], attachments=[png()])
        reply = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=staff["id"],
            content="staff reply",
            attachments=[text()],
        )
        file_ids = {ticket["attachments"][0]["id"], reply["attachments"][0]["id"]}

        _purge(user["id"])

        assert set(attachments.orphaned_file_ids()) == file_ids

        attachments.delete_files(attachments.orphaned_file_ids())

        assert not any(_file_exists(file_id) for file_id in file_ids)

    def test_purging_a_replier_orphans_only_their_reply_files(self, user):
        staff = factories.Sysadmin()
        ticket = _create_ticket(user["id"], attachments=[png()])
        own = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=user["id"],
            content="author reply",
            attachments=[text()],
        )
        staff_reply = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=staff["id"],
            content="staff reply",
            attachments=[text("staff.txt")],
        )

        _purge(staff["id"])

        assert attachments.orphaned_file_ids() == [staff_reply["attachments"][0]["id"]]

        attachments.delete_files(attachments.orphaned_file_ids())

        assert _file_exists(ticket["attachments"][0]["id"])
        assert _file_exists(own["attachments"][0]["id"])

    def test_soft_deleting_a_user_orphans_nothing(self, user):
        _create_ticket(user["id"], attachments=[png()])

        call_action("user_delete", id=user["id"])

        assert attachments.orphaned_file_ids() == []


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestOrphans:
    def test_raw_sql_delete_leaves_an_orphan_that_can_be_cleaned(self, user):
        ticket = _create_ticket(user["id"], attachments=[png()])
        kept = _create_ticket(user["id"], attachments=[png("kept.png")])
        file_id = ticket["attachments"][0]["id"]

        model.Session.execute(sa.delete(Ticket.__table__).where(Ticket.__table__.c.id == ticket["id"]))
        model.Session.commit()

        assert attachments.orphaned_file_ids() == [file_id]

        attachments.delete_files(attachments.orphaned_file_ids())

        assert not _file_exists(file_id)
        assert _file_exists(kept["attachments"][0]["id"])
        assert attachments.orphaned_file_ids() == []

    def test_cli_dry_run_reports_without_deleting(self, user, cli):
        from ckanext.issues.cli import issues  # noqa: PLC0415

        ticket = _create_ticket(user["id"], attachments=[png()])
        file_id = ticket["attachments"][0]["id"]
        model.Session.execute(sa.delete(Ticket.__table__).where(Ticket.__table__.c.id == ticket["id"]))
        model.Session.commit()

        result = cli.invoke(issues, ["clean-attachments", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert file_id in result.output
        assert _file_exists(file_id)

        result = cli.invoke(issues, ["clean-attachments"])
        assert result.exit_code == 0, result.output
        assert not _file_exists(file_id)


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestAccess:
    def _file(self, user: dict[str, Any]) -> tuple[dict[str, Any], str]:
        ticket = _create_ticket(user["id"], attachments=[png()])
        return ticket, ticket["attachments"][0]["id"]

    def test_author_can_download(self, user):
        _ticket, file_id = self._file(user)

        assert call_auth("files_permission_download_file", {"user": user["name"]}, id=file_id)

    def test_sysadmin_can_download(self, user, sysadmin):
        _ticket, file_id = self._file(user)

        assert call_auth("files_permission_download_file", {"user": sysadmin["name"]}, id=file_id)

    def test_other_users_cannot_download(self, user):
        _ticket, file_id = self._file(user)
        stranger = factories.User()

        with pytest.raises(tk.NotAuthorized):
            call_auth("files_permission_download_file", {"user": stranger["name"]}, id=file_id)

    def test_reply_files_follow_the_ticket(self, ticket, sysadmin):
        message = call_action(
            "issues_message_create",
            ticket_id=ticket["id"],
            author_id=sysadmin["id"],
            content="see attached",
            attachments=[text()],
        )
        file_id = message["attachments"][0]["id"]

        assert call_auth("files_permission_download_file", {"user": ticket["author"]["name"]}, id=file_id)
        with pytest.raises(tk.NotAuthorized):
            call_auth("files_permission_download_file", {"user": factories.User()["name"]}, id=file_id)

    def test_even_the_author_cannot_change_files_through_the_files_api(self, user):
        _ticket, file_id = self._file(user)

        with pytest.raises(tk.NotAuthorized):
            call_auth("files_file_delete", {"user": user["name"]}, id=file_id)

    def test_download_route_checks_access(self, app, user):
        _ticket, file_id = self._file(user)
        url = tk.url_for("files.dispatch_download", file_id=file_id)

        assert app.get(url, headers=_auth(user["id"])).status_code == 200
        assert app.get(url, headers=_auth(factories.User()["id"]), status=403).status_code == 403


@_apply(with_files)
@pytest.mark.usefixtures("with_attachments")
class TestViews:
    def test_reply_with_a_file(self, app, ticket):
        resp = app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "a reply", "attachments": (BytesIO(PNG), "shot.png")},
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200
        assert "msg-attachment" in resp.body
        assert "shot.png" in resp.body

    def test_empty_file_input_is_ignored(self, app, ticket):
        resp = app.post(
            tk.url_for("issues.add_message", ticket_id=ticket["id"]),
            data={"content": "a reply", "attachments": (BytesIO(b""), "")},
            headers=_auth(ticket["author"]["id"]),
        )

        assert resp.status_code == 200
        assert call_action("issues_ticket_show", id=ticket["id"])["messages"][-1]["attachments"] == []

    def test_new_ticket_with_a_file(self, app, user):
        resp = app.post(
            tk.url_for("issues.add_ticket"),
            data={
                "subject": "Preview issue",
                "category": "Data request",
                "text": "The map stays empty.",
                "attachments": (BytesIO(PNG), "shot.png"),
            },
            headers=_auth(user["id"]),
        )

        assert resp.status_code == 200
        ticket = call_action("issues_ticket_show", id=_latest(user))
        assert [f["name"] for f in ticket["attachments"]] == ["shot.png"]

    @pytest.mark.ckan_config("ckanext.issues.attachments.max_size", 10)
    def test_rejected_file_is_reported_in_the_modal(self, app, user):
        resp = app.post(
            tk.url_for("issues.add_ticket"),
            data={
                "subject": "Preview issue",
                "category": "Data request",
                "text": "The map stays empty.",
                "attachments": (BytesIO(PNG), "shot.png"),
            },
            headers=_auth(user["id"]),
        )

        assert "shot.png is larger than" in resp.body
        assert "Please choose the files again." in resp.body
        assert Ticket.count_open_for_author(user["id"]) == 0

    def test_ticket_page_shows_the_upload_control_and_files(self, app, user):
        ticket = _create_ticket(user["id"], attachments=[png()])

        resp = app.get(tk.url_for("issues.ticket_read", ticket_id=ticket["id"]), headers=_auth(user["id"]))

        assert 'name="attachments"' in resp.body
        assert 'hx-encoding="multipart/form-data"' in resp.body
        assert tk.url_for("files.dispatch_download", file_id=ticket["attachments"][0]["id"]) in resp.body


def _latest(user: dict[str, Any]) -> int:
    from ckan import model

    return model.Session.query(Ticket.id).filter(Ticket.author_id == user["id"]).order_by(Ticket.id.desc()).scalar()


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestWithoutFilesPlugin:
    """Default test config: ckanext-files installed but not enabled."""

    def test_attachments_are_rejected(self, user):
        with pytest.raises(tk.ValidationError) as err:
            _create_ticket(user["id"], attachments=[png()])

        assert "attachments" in err.value.error_dict

    def test_tickets_work_and_have_no_attachments(self, user):
        ticket = _create_ticket(user["id"])

        assert ticket["attachments"] == []

    def test_no_upload_control(self, app, user):
        ticket = _create_ticket(user["id"])

        resp = app.get(tk.url_for("issues.ticket_read", ticket_id=ticket["id"]), headers=_auth(user["id"]))

        assert 'name="attachments"' not in resp.body
