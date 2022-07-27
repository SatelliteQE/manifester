import click

from manifester import Manifester


# To do: add a command for returning subscription pools
@click.group
def cli():
    pass


@cli.command()
@click.option(
    "--manifest_category",
    type=str,
    help="Category of manifest (golden_ticket or robottelo_automation by default)",
)
@click.option(
    "--allocation_name", type=str, help="Name of upstream subscription allocation"
)
def get_manifest(manifest_category, allocation_name):
    manifester = Manifester(manifest_category, allocation_name)
    manifester.create_subscription_allocation()
    for sub in manifester.subscription_data:
        manifester.process_subscription_pools(
            subscription_pools=manifester.subscription_pools,
            subscription_data=sub,
        )
    manifester.trigger_manifest_export()
