#!/usr/bin/env python3
import logging
import sys

import click
from colorama import init

from dd.dd_api import counts_by_product_id, get_products

# use Colorama to make Termcolor work on Windows too
init()


@click.command()
@click.option(
    "-t",
    "--token",
    required=False,
    prompt=True,
    hide_input=True,
    confirmation_prompt=True,
    envvar="DD_API_TOKEN",
    help="DD API token",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Switch between INFO and DEBUG logging modes",
)
def cli(token=None, verbose=False):
    """Simple program that check a commit message. Try ./get_data.py -v"""

    logger.info("Collecting data")

    if verbose:
        # click.echo(user)
        # click.echo(password)
        click.echo(verbose)

    products = get_products()
    results = {name: counts_by_product_id(id) for name, id in products.items()}
    print(results)


logger = logging.getLogger("nabla.get_data")
logger.setLevel(logging.INFO)
stdoutlog = logging.StreamHandler(sys.stdout)
logger.addHandler(stdoutlog)

if __name__ == "__main__":
    cli(None)


# python3 get_data.py
