from __future__ import annotations

from typing import TYPE_CHECKING

from ckan.logic.schema import validator_args

from ckanext.issues.model import Ticket

if TYPE_CHECKING:
    from ckan import types


@validator_args
def ticket_create(
    not_missing: types.Validator,
    not_empty: types.Validator,
    unicode_safe: types.Validator,
    user_id_or_name_exists: types.Validator,
    issues_category_validator: types.Validator,
) -> types.Schema:
    return {
        "subject": [not_empty, unicode_safe],
        "category": [not_missing, unicode_safe, issues_category_validator],
        "text": [not_empty, unicode_safe],
        "author_id": [not_missing, unicode_safe, user_id_or_name_exists],
    }


@validator_args
def ticket_show(
    not_missing: types.Validator,
    unicode_safe: types.Validator,
    ticket_id_exists: types.Validator,
) -> types.Schema:
    return {"id": [not_missing, unicode_safe, ticket_id_exists]}


@validator_args
def ticket_delete(
    ignore_missing: types.Validator,
    unicode_safe: types.Validator,
    ticket_id_exists: types.Validator,
) -> types.Schema:
    return {"id": [ignore_missing, unicode_safe, ticket_id_exists]}


@validator_args
def ticket_assign(
    not_missing: types.Validator,
    ignore_missing: types.Validator,
    ignore_empty: types.Validator,
    unicode_safe: types.Validator,
    ticket_id_exists: types.Validator,
    issues_assignee_validator: types.Validator,
) -> types.Schema:
    return {
        "id": [not_missing, unicode_safe, ticket_id_exists],
        "assignee_id": [
            ignore_missing,
            ignore_empty,
            unicode_safe,
            issues_assignee_validator,
        ],
    }


@validator_args
def ticket_update(
    not_missing: types.Validator,
    ignore_missing: types.Validator,
    unicode_safe: types.Validator,
    ignore: types.Validator,
    one_of: types.ValidatorFactory,
    ticket_id_exists: types.Validator,
) -> types.Schema:
    return {
        "id": [not_missing, unicode_safe, ticket_id_exists],
        "status": [
            ignore_missing,
            unicode_safe,
            one_of(
                [
                    Ticket.Status.opened,
                    Ticket.Status.closed,
                ],
            ),
        ],
        "__extras": [ignore],
        "__junk": [ignore],
    }


@validator_args
def message_create(
    not_missing: types.Validator,
    not_empty: types.Validator,
    unicode_safe: types.Validator,
    user_id_or_name_exists: types.Validator,
    ticket_id_exists: types.Validator,
) -> types.Schema:
    return {
        "ticket_id": [not_missing, unicode_safe, ticket_id_exists],
        "author_id": [not_missing, unicode_safe, user_id_or_name_exists],
        "content": [not_empty, unicode_safe],
    }


@validator_args
def message_delete(
    not_missing: types.Validator,
    unicode_safe: types.Validator,
    message_id_exists: types.Validator,
) -> types.Schema:
    return {
        "id": [not_missing, unicode_safe, message_id_exists],
    }


@validator_args
def message_update(
    not_missing: types.Validator,
    not_empty: types.Validator,
    unicode_safe: types.Validator,
    message_id_exists: types.Validator,
) -> types.Schema:
    return {
        "id": [not_missing, unicode_safe, message_id_exists],
        "content": [not_empty, unicode_safe],
    }
