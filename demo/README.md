# Demo video

`scenario.py` is the ckanext-issues walkthrough (about 2 minutes), recorded
with [ckan-demo](../../ckan-demo/).

| Scene | Who | What it shows |
| --- | --- | --- |
| `01-open-ticket` | user | header button → new-ticket modal (Markdown) → ticket page → My tickets |
| `02-staff-triage` | staff | queue tabs → Unassigned → assign to me → reply (Ctrl+Enter), "Support" tag |
| `03-conversation` | user | sees the reply, answers, edits their message |
| `04-staff-close` | staff | close with confirmation, read-only closed ticket |
| `05-author-closed` | user | closed notice |
| `06-staff-manage` | staff | Closed view, bulk actions and the red delete confirmation, columns, dark theme |

## Record

```sh
pip install -e path/to/ckan-demo && python -m playwright install chromium

export CKAN_INI=/path/to/ckan.ini      # or pass --ckan-ini
ckan-demo record demo/scenario.py --reset
```

The scenario seeds **locally** (`@scenario.setup(local=True)`, see ckan-demo's [Seeding](../../ckan-demo/docs/seeding.md)
guide), so it needs the portal's `ckan.ini` (`CKAN_INI` or `--ckan-ini`) and
no API token. The output folder comes from `[tool.ckan-demo]` in the
extension's `pyproject.toml`. It loads the same sample backlog as the e2e tests
(`ckanext/issues/tests/e2e/sample_data.py`, through `seed.seed_tickets()`),
backdated over the past weeks.

- `--reset` **deletes every ticket** on the portal before loading the
  backlog, so each take starts the same. Use it on a development portal only.
  Without it, only the ticket a previous take created is removed, and the
  backlog is loaded only into an empty queue.
- The demo users `maria`, `tom`, `aisha` and the sysadmin `anna-support` are
  created (or reset) with the password `correct horse battery staple`.

The video lands in `demo/output/ckanext-issues.mp4`.
Background music goes in `demo/music.mp3`.

See ckan-demo's docs for `--speed`, `--no-captions`, `--gif` and the rest.
