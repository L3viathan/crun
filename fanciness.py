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


class ColorfulCommand(click.Command):
    def get_usage(self, ctx):
        formatter = self.make_formatter(ctx)
        self.format_usage(ctx, formatter)
        return formatter.getvalue().rstrip('\n')

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
            colorful.white(prog),
            args=args,
            prefix=colorful.green(prefix),
        )

    def write_heading(self, heading):
        return super().write_heading(colorful.green(heading))

    # def write_dl(self, rows, col_max=30, col_spacing=2):
    #     ...


class LogColorizer:
    @staticmethod
    def arg_wrapper(log_color, arg):
        """
        Wrap an argument in white non-destructively.

        If we'd use colorful.white() directly, we'd lose the style of the
        surrounding log level.
        """
        return "{}{}{}".format(colorful.white.style[0], arg, log_color.style[0])

    def __getattr__(self, attr):
        """
        Handle calls to log.debug, log.warning, etc.

        We mostly hand those calls off to logger.*, but wrap the message in an
        appropriate color based on the log level of the message. Arguments are
        colored differently.
        """
        log_color = COLORS[attr]

        def wrapper(message, *args):
            return getattr(logger, attr)(
                log_color(message),
                *(self.arg_wrapper(log_color, arg) for arg in args)
            )

        return wrapper

    def echo(self, message, *args):
        print(str(colorful.cyan(message)) % tuple(colorful.white(arg) for arg in args))


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
