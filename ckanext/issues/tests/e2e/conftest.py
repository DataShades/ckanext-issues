"""Browser (Playwright) fixtures.

The CKAN test app is served from a background thread, so tests seed data with
the usual factories and then drive a real browser against it.

Run with::

    pip install -e '.[e2e]' && playwright install chromium
    pytest ckanext/issues/tests/e2e

Environment variables:

- ``PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH``: use a system Chromium instead of the
  one downloaded by ``playwright install`` (e.g. on NixOS).
- ``ISSUES_E2E_SCREENSHOTS``: directory to save named screenshots of key UI
  states into, for design review, e.g. ``e2e-screenshots`` (relative to the
  current directory). Unset, no screenshots are taken.
"""

from __future__ import annotations

import importlib.util
import os
import re
import socket
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from werkzeug.serving import make_server

from ckan.plugins import toolkit as tk
from ckan.tests import factories

from ckanext.issues.tests.e2e import seed

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from playwright.sync_api import BrowserContext, Page

if importlib.util.find_spec("pytest_playwright") is None:
    # The e2e extra is not installed: skip the browser tests.
    collect_ignore_glob = ["test_*.py"]

PASSWORD = "correct horse battery staple"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    here = Path(__file__).parent
    for item in items:
        if here in Path(item.fspath).parents:
            item.add_marker(pytest.mark.e2e)
            # test-core.ini pins the session cookie to test.ckan.net; the
            # browser would drop it on 127.0.0.1 and never stay logged in.
            item.add_marker(pytest.mark.ckan_config("SESSION_COOKIE_DOMAIN", None))


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict[str, Any]) -> dict[str, Any]:
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if executable:
        return {**browser_type_launch_args, "executable_path": executable}
    return browser_type_launch_args


@pytest.fixture
def live_server_socket(ckan_config: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[socket.socket]:
    """Reserve a port and point ``ckan.site_url`` at it before the app is built.

    Some URLs (e.g. the tables' data endpoint) are absolute, so the test-core
    ``http://test.ckan.net`` would send the browser elsewhere.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    monkeypatch.setitem(ckan_config, "ckan.site_url", f"http://127.0.0.1:{sock.getsockname()[1]}")

    yield sock

    sock.close()


@pytest.fixture
def live_server(live_server_socket: socket.socket, app: Any, with_plugins: None, clean_db: None) -> Iterator[str]:
    """Serve the CKAN test app on a free local port; yields its base URL."""
    server = make_server("127.0.0.1", 0, app.app, threaded=True, fd=live_server_socket.fileno())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield str(tk.config["ckan.site_url"])

    server.shutdown()
    thread.join()


@pytest.fixture
def login_as(new_context: Callable[..., BrowserContext], live_server: str) -> Callable[..., Page]:
    """Return a factory that opens a page logged in as the given user.

    Each call uses its own browser context, so a test can drive several users
    side by side.
    """

    def login(user: dict[str, Any], viewport: dict[str, int] | None = None) -> Page:
        context = new_context(base_url=live_server, viewport=viewport or {"width": 1440, "height": 900})
        page = context.new_page()
        page.goto("/user/login")
        page.locator("#field-login").fill(user["name"])
        page.locator("#field-password").fill(PASSWORD)
        page.get_by_role("button", name="Login").click()
        page.wait_for_url(lambda url: "/user/login" not in url)
        return page

    return login


@pytest.fixture
def staff(live_server: str) -> dict[str, Any]:
    name, fullname = next(iter(seed.STAFF.items()))
    return factories.Sysadmin(name=name, fullname=fullname, password=PASSWORD)


@pytest.fixture
def authors(live_server: str) -> dict[str, dict[str, Any]]:
    return {
        name: factories.User(name=name, fullname=fullname, password=PASSWORD) for name, fullname in seed.AUTHORS.items()
    }


@pytest.fixture
def tickets(authors: dict[str, dict[str, Any]], staff: dict[str, Any]) -> list[dict[str, Any]]:
    """The sample support queue from ``seed.TICKETS``."""
    return seed.seed_tickets(authors, staff)


@pytest.fixture(scope="session")
def screenshots_dir() -> Path | None:
    """The ``ISSUES_E2E_SCREENSHOTS`` directory, created once per run.

    A bad path stops the run with one clear error instead of failing every
    test that takes a screenshot.
    """
    target = os.environ.get("ISSUES_E2E_SCREENSHOTS")
    if not target:
        return None

    path = Path(target).expanduser().resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        pytest.exit(f"ISSUES_E2E_SCREENSHOTS: cannot create {path}: {e.strerror}", returncode=4)

    return path


@pytest.fixture
def snap(request: pytest.FixtureRequest, screenshots_dir: Path | None) -> Callable[[Page, str], None]:
    """Save a full-page screenshot named after the test, if enabled.

    Screenshots are opt-in through ``ISSUES_E2E_SCREENSHOTS`` so regular runs
    stay fast and leave no files behind.
    """
    test_name = re.sub(r"\W+", "-", request.node.name).strip("-")

    def take(page: Page, name: str) -> None:
        if screenshots_dir is None:
            return
        # Settle htmx swaps and CSS transitions before capturing.
        page.wait_for_load_state("networkidle")
        page.screenshot(path=screenshots_dir / f"{test_name}--{name}.png", full_page=True, animations="disabled")

    return take
