[![Tests](https://github.com/DataShades/ckanext-issues/actions/workflows/test.yml/badge.svg)](https://github.com/DataShades/ckanext-issues/actions/workflows/test.yml)

# ckanext-issues

A CKAN extension for managing and tracking support tickets ("issues") from
within the CKAN interface.

![Screenshot of the support ticket modal](https://raw.githubusercontent.com/DataShades/ckanext-issues/master/doc/images/preview.png)

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

TODO:
* Add file uploads to messages.

## Requirements

Compatibility with core CKAN versions:

| CKAN version    | Compatible?   |
| --------------- | ------------- |
| 2.10            | yes           |
| 2.11            | yes           |
| 2.12            | yes           |

Requires `ckanext-tables` to be installed and enabled.

## Installation

1. Activate your CKAN virtual environment, for example:

     . /usr/lib/ckan/default/bin/activate

2. Clone the source and install it on the virtualenv

    git clone https://github.com/DataShades/ckanext-issues.git
    cd ckanext-issues
    pip install -e .

   This also pulls in `ckanext-tables`.

3. Add `tables issues` to the `ckan.plugins` setting in your CKAN
   config file (`issues` must be listed after `tables`).

4. Run the database migrations:

     ckan db upgrade -p issues

5. Restart CKAN.


## Config settings

See the available config options in [`config_declaration.yaml`](ckanext/issues/config_declaration.yaml).

## Developer installation

    git clone https://github.com/DataShades/ckanext-issues.git
    cd ckanext-issues
    pip install -e '.[test]'


## Tests

To run the tests, do:

    pytest --ckan-ini=test.ini


## License

[AGPL](https://www.gnu.org/licenses/agpl-3.0.en.html)
