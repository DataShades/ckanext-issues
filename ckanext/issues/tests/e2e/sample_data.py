"""Sample users and support tickets, as plain data.

No CKAN imports, so tools outside CKAN (the ckan-demo scenario) can read it
too. ``seed.py`` loads it into a portal.
"""

from __future__ import annotations

from typing import TypedDict


class TicketSpec(TypedDict):
    author: str
    subject: str
    category: str
    text: str
    status: str
    assignee: bool
    age_days: float
    messages: list[tuple[str, str]]


AUTHORS: dict[str, str] = {
    "maria": "Maria Kovalenko",
    "tom": "Tom Becker",
    "aisha": "Aisha Rahman",
}

STAFF: dict[str, str] = {"anna-support": "Anna Lindqvist"}

# ``messages`` are (who, content) pairs; ``who`` is "author" or "staff".
TICKETS: list[TicketSpec] = [
    {
        "author": "maria",
        "subject": "Air quality dataset stopped updating after 3 March",
        "category": "Bug report",
        "text": (
            "The **Hourly air quality - Kyiv** dataset has not received new rows since 3 March.\n\n"
            "Steps to reproduce:\n\n"
            "1. Open the dataset page\n"
            "2. Preview the `measurements.csv` resource\n"
            "3. Sort by `timestamp` descending\n\n"
            "The latest record is `2026-03-03T23:00:00Z`. Our dashboard depends on this feed."
        ),
        "status": "opened",
        "assignee": True,
        "age_days": 6,
        "messages": [
            ("staff", "Thanks for the report, Maria. The harvester job is failing on a schema change upstream."),
            ("author", "Good to know. Is there an ETA? We have a public report due on Friday."),
            ("staff", "We are deploying a fix today and will backfill the missing days afterwards."),
        ],
    },
    {
        "author": "maria",
        "subject": "Request: monthly municipal budget data in CSV",
        "category": "Data request",
        "text": "Could you publish the municipal budget tables as CSV in addition to the PDF reports?",
        "status": "opened",
        "assignee": False,
        "age_days": 1.5,
        "messages": [],
    },
    {
        "author": "maria",
        "subject": "Typo in the organisation description",
        "category": "Other",
        "text": "The *Department of Transport* page says “Transprot” in the first sentence.",
        "status": "closed",
        "assignee": True,
        "age_days": 21,
        "messages": [
            ("staff", "Fixed, thank you!"),
        ],
    },
    {
        "author": "tom",
        "subject": "API returns 500 when filtering by resource format",
        "category": "Bug report",
        "text": (
            "Calling `package_search` with `fq=res_format:GeoJSON` returns HTTP 500.\n\n"
            "```\ncurl 'https://portal.example/api/3/action/package_search?fq=res_format:GeoJSON'\n```"
        ),
        "status": "opened",
        "assignee": True,
        "age_days": 3,
        "messages": [
            ("staff", "Reproduced. It only happens when the format contains capital letters."),
        ],
    },
    {
        "author": "tom",
        "subject": "Bulk download for all transport datasets",
        "category": "Feature request",
        "text": "It would help researchers a lot to download every dataset in a group as a single ZIP archive.",
        "status": "opened",
        "assignee": False,
        "age_days": 9,
        "messages": [],
    },
    {
        "author": "aisha",
        "subject": "Cannot upload files larger than 100 MB",
        "category": "Bug report",
        "text": "The upload form fails with no error message when the file is larger than ~100 MB.",
        "status": "closed",
        "assignee": True,
        "age_days": 30,
        "messages": [
            ("staff", "The limit is configured on purpose. For larger files please link to external storage."),
            ("author", "Understood, thanks for clarifying."),
        ],
    },
    {
        "author": "aisha",
        "subject": "Dark mode makes chart labels unreadable",
        "category": "Other",
        "text": "With dark mode on, the axis labels in the resource chart view are dark grey on black.",
        "status": "opened",
        "assignee": False,
        "age_days": 0.2,
        "messages": [],
    },
]
