#! coding: utf-8

import click

from .core import WebHandler
from .webui import app
from . import __version__


def run_server(file_path=None,
               loop_interval=60,
               auto_open_browser=True,
               app_kwargs=None):
    wh = WebHandler(
        app,
        file_path=file_path,
        loop_interval=loop_interval,
        auto_open_browser=auto_open_browser,
        app_kwargs=app_kwargs)
    wh.run()


@click.command(context_settings={
    "help_option_names": ["-h", "--help"],
    "ignore_unknown_options": True,
})
@click.version_option(__version__, "-V", "--version", prog_name="onwebchange")
@click.option("--file-path", "-f", default=None, help="file_path for storage")
@click.option(
    "--auto-open-browser",
    "-a",
    is_flag=True,
    help="auto_open_browser if set",
)
@click.option(
    "--loop-interval",
    "-i",
    default=60,
    help="check loop interval",
)
# @click.argument("app_kwargs", nargs=-1, type=click.UNPROCESSED)
def main(*args, **kwargs):
    run_server(*args, **kwargs)


if __name__ == "__main__":
    main()
