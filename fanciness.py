import logging
import click
import colorful

logging.basicConfig(
    style="{",
    format="{} {} {}".format(colorful.green("{asctime}"), "›", "{message}"),
    datefmt="%H:%M:%S",
    # level=logging.DEBUG,
)
logger = logging.getLogger("runner")


COLORS = {
    "debug": colorful.brown,
    "info": colorful.cyan,
    "warning": colorful.orange,
    "error": colorful.red,
    "critical": colorful.bold_red,
}


class LogColorizer:
    def __getattr__(self, attr):
        def wrapper(message, *args):
            return getattr(logger, attr)(
                COLORS[attr](message), *(colorful.white(arg) for arg in args)
            )

        return wrapper


log = LogColorizer()


def _set_verbosity(_, __, val):
    if val > 1:
        logger.setLevel(logging.DEBUG)
    elif val:
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.WARNING)


def click_verbosity(fn, pass_through=False):
    return click.option(
        "--verbose",
        "-v",
        count=True,
        callback=_set_verbosity,
        expose_value=pass_through,
    )(fn)
