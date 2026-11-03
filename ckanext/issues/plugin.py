from __future__ import annotations

from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import types
from ckan.lib.plugins import DefaultTranslation

from ckanext.issues import attachments, mailer
from ckanext.issues import signals as issues_signals


@tk.blanket.blueprints
@tk.blanket.cli
@tk.blanket.actions
@tk.blanket.auth_functions
@tk.blanket.validators
@tk.blanket.helpers
@tk.blanket.config_declarations
class IssuesPlugin(p.SingletonPlugin, DefaultTranslation):
    p.implements(p.IConfigurer)
    p.implements(p.ISignal)
    p.implements(p.ITranslation)

    # Attachments: only when ckanext-files is installed (see attachments.py).
    if attachments.FilesInterface is not None:
        p.implements(attachments.FilesInterface, inherit=True)
    if attachments.CoreFilesInterface is not None and attachments.CoreFilesInterface is not attachments.FilesInterface:
        p.implements(attachments.CoreFilesInterface, inherit=True)

    # IConfigurer

    def update_config(self, config_: tk.CKANConfig) -> None:
        tk.add_template_directory(config_, "templates")
        tk.add_public_directory(config_, "public")
        tk.add_resource("assets", "issues")

    # ISignal

    def get_signal_subscriptions(self) -> types.SignalMapping:
        return {
            issues_signals.ticket_created: [
                mailer.notify_admins_on_new_ticket,
            ],
            issues_signals.message_created: [
                mailer.notify_author_on_new_message,
            ],
            issues_signals.ticket_updated: [
                mailer.notify_author_on_ticket_update,
            ],
            issues_signals.ticket_assigned: [
                mailer.notify_assignee_on_assign,
            ],
        }

    # IFiles

    def files_file_allows(self, context: types.Context, file: Any, operation: str) -> bool | None:
        return attachments.file_allows(context, file, operation)

    def files_owner_allows(self, context: types.Context, owner_type: str, owner_id: str, operation: str) -> bool | None:
        return attachments.owner_allows(context, owner_type, owner_id, operation)
