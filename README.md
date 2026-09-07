[![Tests](https://github.com/DataShades/ckanext-issues/workflows/Tests/badge.svg?branch=main)](https://github.com/DataShades/ckanext-issues/actions)

# ckanext-issues

A CKAN extension for managing and tracking support tickets ("issues") from
within the CKAN interface.

It provides:

* A **support ticket** modal available from the account navigation, so any
  logged-in user can open a ticket with a subject, category and description.
* A **"My Support Requests"** page where users can follow up on their own
  tickets and exchange messages with staff.
* A **sysadmin dashboard** (`/issues/admin`) listing every ticket, with bulk
  actions (close / reopen / remove), per-ticket assignment and a threaded
  conversation view.
* Email notifications (new ticket → sysadmins, new reply / status change →
  ticket author), each toggleable via config.

This extension was extracted from the `admin_panel_support` plugin of
`ckanext-admin-panel`. It no longer depends on `ckanext-admin-panel`; the only
CKAN-extension dependency is [`ckanext-tables`](https://github.com/DataShades/ckanext-tables),
which powers the ticket tables.


## Requirements

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.10            | not tested    |
| 2.11            | yes           |

Requires `ckanext-tables` to be installed and enabled.


## Installation

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/DataShades/ckanext-issues.git
    cd ckanext-issues
    pip install -e .
    pip install -r requirements.txt

3. Add `tables issues` to the `ckan.plugins` setting in your CKAN
   config file (`issues` must be listed after `tables`).

4. Run the database migrations:

     ckan db upgrade -p issues

5. Restart CKAN.


## Config settings

```ini
# Allowed ticket categories (space/newline separated list).
# (optional, default: Feature request, Data request, Bug report, Other)
ckanext.issues.category_list = "Feature request" "Data request" "Bug report" Other

# Email notifications (optional, all default: true)
ckanext.issues.notify_on_new_ticket = true
ckanext.issues.notify_on_new_message = true
ckanext.issues.notify_on_ticket_update = true
```


## Developer installation

    git clone https://github.com/DataShades/ckanext-issues.git
    cd ckanext-issues
    pip install -e '.[test]'


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini


## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
