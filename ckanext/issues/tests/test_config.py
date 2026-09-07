from __future__ import annotations

import pytest

from ckanext.issues import config


@pytest.mark.usefixtures("with_plugins")
class TestTicketCategories:
    def test_default_when_unset(self):
        assert config.get_ticket_categories() == config.DEF_TICKET_CATEGORIES

    @pytest.mark.ckan_config(
        "ckanext.issues.category_list",
        "Feature request\nData request\nBug report",
    )
    def test_one_per_line_keeps_spaces(self):
        assert config.get_ticket_categories() == [
            "Feature request",
            "Data request",
            "Bug report",
        ]

    @pytest.mark.ckan_config(
        "ckanext.issues.category_list",
        "  \n  Feature request  \n\n  Bug report  \n",
    )
    def test_blank_lines_and_padding_are_ignored(self):
        assert config.get_ticket_categories() == ["Feature request", "Bug report"]

    @pytest.mark.ckan_config("ckanext.issues.category_list", "Bug report")
    def test_single_line_is_a_single_category(self):
        assert config.get_ticket_categories() == ["Bug report"]

    @pytest.mark.ckan_config("ckanext.issues.category_list", "   \n  \n ")
    def test_empty_value_falls_back_to_default(self):
        assert config.get_ticket_categories() == config.DEF_TICKET_CATEGORIES


@pytest.mark.usefixtures("with_plugins")
class TestMaxOpenTickets:
    def test_default(self):
        assert config.get_max_open_tickets_per_user() == config.DEF_MAX_OPEN_TICKETS

    @pytest.mark.ckan_config("ckanext.issues.max_open_tickets_per_user", "3")
    def test_reads_the_configured_value(self):
        assert config.get_max_open_tickets_per_user() == 3

    @pytest.mark.ckan_config("ckanext.issues.max_open_tickets_per_user", 0)
    def test_zero_is_returned_verbatim(self):
        assert config.get_max_open_tickets_per_user() == 0


@pytest.mark.usefixtures("with_plugins")
class TestNotificationFlags:
    def test_off_for_the_test_suite_by_default(self):
        # test.ini disables all three notification flags for the whole suite.
        assert not config.get_notify_on_new_ticket()
        assert not config.get_notify_on_new_message()
        assert not config.get_notify_on_ticket_update()

    @pytest.mark.ckan_config("ckanext.issues.notify_on_new_ticket", "true")
    def test_new_ticket_flag_can_be_enabled(self):
        assert config.get_notify_on_new_ticket()

    @pytest.mark.ckan_config("ckanext.issues.notify_on_new_message", "yes")
    def test_new_message_flag_accepts_truthy_strings(self):
        assert config.get_notify_on_new_message()

    @pytest.mark.ckan_config("ckanext.issues.notify_on_ticket_update", "1")
    def test_ticket_update_flag_accepts_truthy_strings(self):
        assert config.get_notify_on_ticket_update()
