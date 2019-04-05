import sys
import logging
import click

COLORS = {
    "debug": "\x1b[38;5;131m",  # brown
    "info": "\x1b[38;5;51m",  # cyan
    "warning": "\x1b[38;5;214m",  # orange
    "error": "\x1b[38;5;196m",  # red
    "critical": "\x1b[1m\x1b[38;5;196m",  # bold red
    "green": "\x1b[38;5;46m",
    "white": "\x1b[38;5;231m",
    "gray": "\x1b[38;5;250m",
}

USE_ANSI_CODES = False


def color_wrap(color, string):
    if not USE_ANSI_CODES:
        return string
    return "{}{}\x1b[39m".format(COLORS.get(color, ""), string)


def color_start(color):
    if not USE_ANSI_CODES:
        return ""
    return COLORS[color]


def setup(color_mode="auto", file=None):
    global USE_ANSI_CODES
    if (
        sys.stderr.isatty()
        and color_mode != "never"
        and (not file or color_mode == "always")
    ):
        USE_ANSI_CODES = True
    logging.basicConfig(
        style="{",
        format="{} {}".format(color_wrap("green", "{asctime}"), "{message}"),
        datefmt="%H:%M:%S",
        # sorry:
        **{"handlers": [logging.FileHandler(file)] for _ in range(1) if file},
    )


logger = logging.getLogger("runner")


class ColorfulCommand(click.Command):
    def get_usage(self, ctx):
        formatter = self.make_formatter(ctx)
        self.format_usage(ctx, formatter)
        return formatter.getvalue().rstrip("\n")

    def get_help(self, ctx):
        formatter = self.make_formatter(ctx)
        self.format_help(ctx, formatter)
        return formatter.getvalue().rstrip("\n")

    def make_formatter(self, ctx):
        return ColoredHelpFormatter(
            width=ctx.terminal_width, max_width=ctx.max_content_width
        )


class ColoredHelpFormatter(click.HelpFormatter):
    def write_usage(self, prog, args="", prefix="Usage: "):
        return super().write_usage(
            color_wrap("white", prog),
            args=args,
            prefix=color_wrap("green", prefix),
        )

    def write_heading(self, heading):
        return super().write_heading(color_wrap("green", heading))

    # def write_dl(self, rows, col_max=30, col_spacing=2):
    #     ...


class LogColorizer:
    @staticmethod
    def arg_wrapper(attr, arg):
        """
        Wrap an argument in white non-destructively.

        If we'd use color_wrap("white", ...) directly, we'd lose the style of the
        surrounding log level.
        """
        return "{}{}{}".format(color_start("white"), arg, color_start(attr))

    def __getattr__(self, attr):
        """
        Handle calls to log.debug, log.warning, etc.

        We mostly hand those calls off to logger.*, but wrap the message in an
        appropriate color based on the log level of the message. Arguments are
        colored differently.
        """

        def wrapper(message, *args, indent=0):
            return getattr(logger, attr)(
                "{}› {}".format("  " * indent, color_wrap(attr, message)),
                *(self.arg_wrapper(attr, arg) for arg in args),
            )

        return wrapper

    def echo(self, message, *args):
        print(
            color_wrap("cyan", message)
            % tuple(color_wrap("white", arg) for arg in args)
        )

    def setLevel(self, level):
        logger.setLevel(getattr(logging, level))


log = LogColorizer()


def _set_verbosity(_, arg, val):
    if val:
        current = logger.getEffectiveLevel()
        if arg.name == "verbose":
            logger.setLevel(min(logging.DEBUG, current - val * 10))
        elif arg.name == "quiet":
            logger.setLevel(max(logging.FATAL, current + val * 10))


def click_verbosity(pass_through=False, level=logging.INFO):
    logger.setLevel(level)

    def wrapper(fn):
        return click.option(
            "--verbose",
            "-v",
            count=True,
            callback=_set_verbosity,
            expose_value=pass_through,
        )(
            click.option(
                "--quiet",
                "-q",
                count=True,
                callback=_set_verbosity,
                expose_value=pass_through,
            )(fn)
        )

    return wrapper
