#! coding: utf-8

import click

from .core import WebHandler
from .webui import app
from . import __version__


def run_server(file_path=None,
               loop_interval=300,
               ignore_auto_open_browser=True,
               host=None,
               port=None,
               username='',
               password=''):
    wh = WebHandler(
        app,
        file_path=file_path,
        loop_interval=loop_interval,
        auto_open_browser=not ignore_auto_open_browser,
        app_kwargs=dict(host=host, port=port),
        username=username,
        password=password)
    wh.run()


@click.command(context_settings={
    "help_option_names": ["-h", "--help"],
    "ignore_unknown_options": True,
})
@click.version_option(__version__, "-V", "--version", prog_name="onwebchange")
@click.option("--file-path", "-f", default=None, help="file_path for storage")
@click.option("--host", default='127.0.0.1', help="web host")
@click.option("--port", '-p', default=9988, help="web port")
@click.option("--username", default='', help="login username")
@click.option("--password", default='', help="login password")
@click.option(
    "--ignore-auto-open-browser",
    "-a",
    is_flag=True,
    help="ignore auto_open_browser",
)
@click.option(
    "--loop-interval",
    "-i",
    default=300,
    help="check loop interval",
)
# @click.argument("app_kwargs", nargs=-1, type=click.UNPROCESSED)
def main(*args, **kwargs):
    run_server(*args, **kwargs)


if __name__ == "__main__":
    main()
