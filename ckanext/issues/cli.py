from __future__ import annotations

import click

from ckanext.issues import attachments

__all__ = ["issues"]


@click.group(short_help="ckanext-issues commands")
def issues() -> None:
    pass


@issues.command("clean-attachments")
@click.option("--dry-run", is_flag=True, help="Only report the orphaned attachments.")
def clean_attachments(*, dry_run: bool) -> None:
    """Delete attachments whose ticket or reply no longer exists."""
    if not attachments.enabled():
        return

    file_ids = attachments.orphaned_file_ids()
    if dry_run:
        for file_id in file_ids:
            click.echo(file_id)
        click.secho(f"{len(file_ids)} orphaned attachment(s)", fg="yellow")
        return

    attachments.delete_files(file_ids)
    click.secho(f"Deleted {len(file_ids)} orphaned attachment(s)", fg="green")
