"""Defines the CLI commands for Manifester."""
import os
from pathlib import Path

import click

from manifester import Manifester, helpers
from manifester.logger import _logger as logger
from manifester.settings import settings


# To do: add a command for returning subscription pools
@click.group
def cli():
    """Command-line interface for manifester."""
    pass


@cli.command()
@click.option(
    "--manifest-category",
    type=str,
    help="Category of manifest (golden_ticket or robottelo_automation by default)",
)
@click.option("--allocation-name", type=str, help="Name of upstream subscription allocation")
@click.option("--requester", type=str, default=None)
def get_manifest(manifest_category, allocation_name, requester):
    """Return a subscription manifester based on the settings for the provided manifest_category."""
    manifester = Manifester(manifest_category, allocation_name, requester=requester)
    manifester.create_subscription_allocation()
    for sub in manifester.subscription_data:
        manifester.process_subscription_pools(
            subscription_pools=manifester.subscription_pools,
            subscription_data=sub,
        )
    return manifester.trigger_manifest_export()


@cli.command()
@click.argument("allocations", type=str, nargs=-1)
@click.option(
    "--all",
    "all_",
    is_flag=True,
    default=False,
    help="Delete all subscription allocations in inventory",
)
@click.option(
    "--remove-manifest-file",
    is_flag=True,
    default=False,
    help="Delete local manifest files in addition to upstream subscription allocations",
)
def delete(allocations, all_, remove_manifest_file):
    """Delete subscription allocations in inventory and optionally delete local manifest files."""
    inv = helpers.load_inventory_file(Path(settings.inventory_path))
    for num, allocation in enumerate(inv):
        if str(num) in allocations or allocation.get("name") in allocations or all_:
            Manifester(minimal_init=True).delete_subscription_allocation(
                uuid=allocation.get("uuid")
            )
            if remove_manifest_file:
                manifester_directory = (
                    Path(os.environ["MANIFESTER_DIRECTORY"]).resolve()
                    if "MANIFESTER_DIRECTORY" in os.environ
                    else Path()
                )
                Path(
                    f"{manifester_directory}/manifests/{allocation.get('name')}_manifest.zip"
                ).unlink()


@cli.command()
@click.option("--details", is_flag=True, help="Display full inventory details")
@click.option("--sync", is_flag=True, help="Fetch inventory data from RHSM before displaying")
@click.option("--offline-token", type=str, default=None)
def inventory(details, sync, offline_token):
    """Display the local inventory file's contents."""
    border = "-" * 38
    if sync:
        helpers.update_inventory(Manifester(minimal_init=True, offline_token=offline_token).subscription_allocations)
    inv = helpers.load_inventory_file(Path(settings.inventory_path))
    if not details:
        logger.info("Displaying local inventory data")
        click.echo(border)
        click.echo(f"| {'Index'} | {'Allocation Name':<26} |")
        click.echo(border)
        for num, allocation in enumerate(inv):
            click.echo(f"| {num:<5} | {allocation['name']:<26} |")
            click.echo(border)
    else:
        logger.info("Displaying detailed local inventory data")
        for num, allocation in enumerate(inv):
            click.echo(f"{num}:")
            for key, value in allocation.items():
                click.echo(f"{'':<4}{key}: {value}")
