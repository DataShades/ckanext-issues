"""File attachments on tickets and replies, backed by ckanext-files.

ckanext-files is optional. Everything that touches it lives here, and every
public function is safe to call when it is missing: :func:`enabled` is false,
listing returns nothing and deleting is a no-op.

Each file is owned by what it is attached to: the opening text by the ticket
(``issues_ticket``), a reply by its message (``issues_message``). Ownership is
pinned, and access is decided by :func:`file_allows`, which ckanext-files
calls through its ``IFiles`` interface: whoever can see the ticket can
download its files; nobody may change them through the files API.

On CKAN 2.12+ ckanext-files stores files in core's tables and storages, so
the same calls work on every supported CKAN version.
"""

from __future__ import annotations

import fnmatch
import functools
import logging
import uuid
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import authz, model

from ckanext.issues import config

if TYPE_CHECKING:
    from ckan import types

    from ckanext.issues.types import DictizedAttachment

try:
    from ckanext.files import shared as files_shared
    from ckanext.files.interfaces import IFiles as FilesInterface
except ImportError:
    files_shared = None
    FilesInterface = None

try:
    # CKAN 2.12+. ckanext-files' own auth asks FilesInterface, core's file
    # routes ask this one; the plugin implements both.
    from ckan.plugins.interfaces import IFiles as CoreFilesInterface
except ImportError:
    CoreFilesInterface = None

log = logging.getLogger(__name__)

OWNER_TICKET = "issues_ticket"
OWNER_MESSAGE = "issues_message"
OWNER_TYPES = (OWNER_TICKET, OWNER_MESSAGE)

FIELD = "attachments"

_KIB = 1024


def installed() -> bool:
    """Whether ckanext-files can be imported."""
    return files_shared is not None


def enabled() -> bool:
    """Whether attachments are available: ckanext-files is installed and loaded."""
    return installed() and p.plugin_loaded("files")


def uploads_allowed() -> bool:
    """Whether new files may be attached (existing ones stay visible either way)."""
    return enabled() and config.get_attachments_max_files() > 0 and is_storage_usable()


def _storage_name() -> str:
    return config.get_attachments_storage() or files_shared.config.default_storage()


def is_storage_usable() -> bool:
    """Whether the attachment storage exists and is private.

    A public storage serves files without asking :func:`file_allows`, so
    anyone with the link could read a ticket's attachments. When the storage
    can't be used, the reason is logged once and uploads are turned off.
    """
    name = _storage_name()
    try:
        storage = files_shared.get_storage(name)
    except files_shared.exc.UnknownStorageError:
        _log_once(f"storage {name!r} is not configured")
        return False

    settings = storage.settings
    # `public` flags a storage served without checks; public folder storages
    # (ckan:fs:public, files:public_fs) are exposed by the web server and
    # recognisable by their `public_prefix`.
    if tk.asbool(getattr(settings, "public", False)) or hasattr(settings, "public_prefix"):
        _log_once(f"storage {name!r} is public; attachments need a private storage")
        return False

    return True


@functools.cache
def _log_once(reason: str) -> None:
    log.error("File attachments are disabled: %s (see ckanext.issues.attachments.storage)", reason)


def _type_allowed(content_type: str, allowed: list[str]) -> bool:
    if not allowed:
        return True
    content_type = (content_type or "").lower()
    return any(fnmatch.fnmatchcase(content_type, pattern) for pattern in allowed)


def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < _KIB or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= _KIB
    return f"{size} B"


def prepare_uploads(value: Any) -> list[Any]:
    """Validate uploaded files and turn them into ckanext-files ``Upload``\\ s.

    Accepts one upload or a list of them (werkzeug ``FileStorage``, bytes,
    file objects; anything ckanext-files can read). Empty file inputs are
    dropped. The content type is detected from the file content.

    Raises:
        ckan.plugins.toolkit.Invalid: with every problem found, one per line
    """
    items = value if isinstance(value, (list, tuple)) else [value]
    items = [item for item in items if item is not None and item != "" and not _is_empty_file_input(item)]
    if not items:
        return []

    if not uploads_allowed():
        raise tk.Invalid(tk._("File attachments are not enabled"))

    max_files = config.get_attachments_max_files()
    if len(items) > max_files:
        raise tk.Invalid(tk._("You can attach up to {n} files").format(n=max_files))

    max_size = config.get_attachments_max_size()
    allowed = config.get_attachments_allowed_types()

    uploads: list[Any] = []
    problems: list[str] = []
    for item in items:
        try:
            upload = files_shared.make_upload(item)
        except TypeError:
            problems.append(tk._("Unsupported upload"))
            continue

        # Also stored as the file's size by ckanext-files.
        upload.size = _real_size(upload)
        name = upload.filename or tk._("file")
        if max_size and upload.size > max_size:
            problems.append(
                tk._("{name} is larger than {limit}").format(name=name, limit=_human_size(max_size)),
            )
        elif not _type_allowed(upload.content_type, allowed):
            problems.append(tk._("{name}: this file type is not allowed").format(name=name))
        else:
            uploads.append(upload)

    if problems:
        raise tk.Invalid("\n".join(problems))

    return uploads


def _real_size(upload: Any) -> int:
    """Size of the upload's content, measured on the stream.

    ``upload.size`` can come from the client: a multipart part may carry its
    own Content-Length header, and file-keeper trusts it. Measure instead,
    so the size limit can't be bypassed. Falls back to the reported size for
    streams that can't seek (only internal Python callers pass those).
    """
    stream = upload.stream
    try:
        position = stream.tell()
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(position)
    except (AttributeError, OSError, ValueError):
        return upload.size
    return size


def _is_empty_file_input(item: Any) -> bool:
    """A file input submitted without a file arrives as a nameless, empty part."""
    filename = getattr(item, "filename", None)
    return filename is not None and not filename


def store(uploads: list[Any], user: str) -> list[str]:
    """Write ``uploads`` to the storage; return the new file ids.

    Call this before creating the ticket or message, then hand the files
    over with :func:`assign`. Storing is the slow, fragile part (big files,
    a server restart mid-upload); doing it first means a failure leaves no
    ticket or reply without its files, at worst a file nobody points to.
    Until assigned, the files belong to ``user``.

    If any file fails, the ones stored so far are deleted again and the
    error is re-raised.

    Permission to attach was checked by the calling action, so the files API
    is called with ``ignore_auth``.
    """
    storage = _storage_name()
    stored: list[str] = []

    try:
        for upload in uploads:
            name = upload.filename or "file"
            # The name also becomes the storage location, which must be
            # unique; store under a random prefix, then restore the real name
            # (renaming only changes the name shown and used for downloads).
            info = tk.get_action("files_file_create")(
                {"ignore_auth": True, "user": user},
                {"name": f"{uuid.uuid4().hex}-{name}", "storage": storage, "upload": upload},
            )
            stored.append(info["id"])
            tk.get_action("files_file_rename")(
                {"ignore_auth": True, "user": user},
                {"id": info["id"], "name": name},
            )
    except Exception:
        log.exception("storing attachments failed after %d of %d file(s)", len(stored), len(uploads))
        model.Session.rollback()
        delete_files(stored)
        raise

    return stored


def assign(owner_type: str, owner_id: Any, file_ids: list[str], user: str) -> None:
    """Give stored files to their (committed) ticket or message, pinned."""
    for file_id in file_ids:
        tk.get_action("files_transfer_ownership")(
            {"ignore_auth": True, "user": user},
            {
                "id": file_id,
                "owner_type": owner_type,
                "owner_id": str(owner_id),
                "pin": True,
                "force": True,
            },
        )


def list_for(owner_type: str, owner_ids: list[Any]) -> dict[str, list[DictizedAttachment]]:
    """Attachments of the given owners, keyed by owner id (as a string)."""
    result: dict[str, list[DictizedAttachment]] = {}
    if not enabled() or not owner_ids:
        return result

    File = files_shared.File  # noqa: N806
    Owner = files_shared.Owner  # noqa: N806

    stmt = (
        sa.select(File, Owner.owner_id)
        .join(Owner, Owner.file_id == File.id)
        .where(Owner.owner_type == owner_type, Owner.owner_id.in_([str(i) for i in owner_ids]))
        .order_by(File.created, File.name)
    )

    for fileobj, owner_id in model.Session.execute(stmt):
        result.setdefault(owner_id, []).append(
            {
                "id": fileobj.id,
                "name": fileobj.name,
                "size": fileobj.size,
                "content_type": fileobj.content_type,
            },
        )

    return result


def file_ids_for(owner_type: str, owner_ids: list[Any]) -> list[str]:
    return [item["id"] for items in list_for(owner_type, owner_ids).values() for item in items]


def delete_files(file_ids: list[str]) -> None:
    """Delete files from the storage and the database.

    Called after the ticket or message is gone, so a failure here leaves an
    orphaned file (logged) rather than a broken thread.
    """
    for file_id in file_ids:
        _delete_file(file_id)


def _delete_file(file_id: str) -> None:
    try:
        tk.get_action("files_file_delete")({"ignore_auth": True}, {"id": file_id})
    except tk.ObjectNotFound:
        pass
    except Exception:
        log.exception("Could not delete attachment %s", file_id)


def orphaned_file_ids() -> list[str]:
    """Attachments whose ticket or message no longer exists.

    Purging a user deletes their tickets and replies through database
    cascades, which skip the delete actions that clean up attachments; a file
    that failed to delete is left behind too. ``ckan issues
    clean-attachments`` removes these.
    """
    if not enabled():
        return []

    from ckanext.issues.model import Ticket, TicketMessage  # noqa: PLC0415

    Owner = files_shared.Owner  # noqa: N806
    ticket_exists = sa.exists().where(sa.cast(Ticket.id, sa.Text) == Owner.owner_id)
    message_exists = sa.exists().where(sa.cast(TicketMessage.id, sa.Text) == Owner.owner_id)
    stmt = sa.select(Owner.file_id).where(
        sa.or_(
            sa.and_(Owner.owner_type == OWNER_TICKET, ~ticket_exists),
            sa.and_(Owner.owner_type == OWNER_MESSAGE, ~message_exists),
        ),
    )
    return list(model.Session.scalars(stmt))


def _owner_ticket_id(owner_type: str, owner_id: str) -> Any:
    from ckanext.issues.model import TicketMessage  # noqa: PLC0415

    if owner_type == OWNER_TICKET:
        return owner_id

    message = TicketMessage.get(owner_id)
    return message.ticket_id if message else None


def file_allows(context: types.Context, file: Any, operation: str) -> bool | None:
    """``IFiles.files_file_allows`` for files owned by tickets and messages.

    Reading (``show``, which also covers downloads) follows access to the
    ticket. Anything else is refused: attachments change only together with
    their ticket or message. Other files are left to the default rules.
    """
    owner = getattr(file, "owner", None)
    if not owner or owner.owner_type not in OWNER_TYPES:
        return None

    if operation != "show":
        return False

    ticket_id = _owner_ticket_id(owner.owner_type, owner.owner_id)
    if ticket_id is None:
        return False

    return authz.is_authorized_boolean("issues_ticket_show", context, {"id": ticket_id})


def owner_allows(_context: types.Context, owner_type: str, _owner_id: str, _operation: str) -> bool | None:
    """``IFiles.files_owner_allows``: no file may be moved to or from our owners
    through the files API."""
    if owner_type in OWNER_TYPES:
        return False
    return None
