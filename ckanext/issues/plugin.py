from __future__ import annotations

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import types

from ckanext.issues import mailer
from ckanext.issues import signals as issues_signals


@tk.blanket.blueprints
@tk.blanket.actions
@tk.blanket.auth_functions
@tk.blanket.validators
@tk.blanket.helpers
class IssuesPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.ISignal)

    # IConfigurer

    def update_config(self, config_: tk.CKANConfig):
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
        }
