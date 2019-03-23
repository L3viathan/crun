import os
import sys
import subprocess
import click
import toml
import colorful

from .fanciness import log, click_verbosity, ColorfulCommand


def run_pipeline(label, command, config):
    log.debug("Resolving pipeline command %s", label)
    for cmd in command["command"]:
        # if we override settings of a command in a pipeline
        if cmd in command:
            log.debug("Overriding config from pipeline command")
            config[cmd].update(command[cmd])
        run_command(cmd, config)  # have to resolve command labels


def get_environment(command):
    if "environment" in command:
        log.debug("Updating environment variables")
        env = os.environ.copy()
        env.update(command["environment"])
        return env
    else:
        return None


def get_options(command):
    if "options" in command:
        log.debug("Adding options")
        return " {}".format(
            " ".join(
                f"--{key}={val}" for (key, val) in command["options"].items()
            )
        )
    else:
        return ""


def run_command(label, config):
    command = get_command(label, config)
    if isinstance(command["command"], list):  # pipeline
        return run_pipeline(label, command, config)

    env = get_environment(command)
    opts = get_options(command)

    cmd = "{}{}".format(command["command"], opts)
    log.info("Running command %s", label)
    try:
        subprocess.run(cmd, env=env, shell=True, check=True)
        log.info("Command %s finished", label)
    except subprocess.CalledProcessError as e:
        if command.get("fail_ok", False):
            return log.info("Command %s finished", label)
        log.error(
            "Command %s returned with non-zero exit code %s",
            label,
            e.returncode,
        )
        if config.get("fail_ok", False) is False:
            raise e


def get_command(command, config):
    if command not in config:
        raise ValueError(f"Command {command} not found in configuration.")
    if (
        not isinstance(config[command], dict)
        or "command" not in config[command]
    ):
        raise ValueError(
            f"Command {command} must be a table, with the command value set."
        )
    return config[command]


def get_config(filename):
    try:
        with open(filename) as f:
            data = toml.load(f)
            if "base" in data:
                data = {**get_config(data["base"]), **data}
        return data
    except FileNotFoundError:
        raise click.BadOptionUsage(
            option_name="--config",
            message=colorful.red(f"Configuration file {filename} not found."),
        )


def apply_overrides(config, ctx):
    def set_recursive(store, dotted_name, value):
        head, _, tail = dotted_name.partition(".")
        if tail:
            store.setdefault(head, {})
            set_recursive(store[head], tail, value)
        else:
            store[head] = value

    remaining = list(ctx.args)
    while remaining:
        option = remaining.pop(0)
        if not option.startswith("--"):  # only options are allowed
            raise click.BadParameter(option)
        if "=" in option:
            option, value = option.split("=", maxsplit=1)
        else:
            try:
                maybe_value = remaining.pop(0)
                if maybe_value.startswith("--"):
                    remaining.insert(0, maybe_value)  # place back option
                    raise IndexError
                value = maybe_value
            except IndexError:
                # no next value or next value is an option -> we have a flag
                value = True

        set_recursive(config, option[2:], value)


@click.command(
    cls=ColorfulCommand,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--config", "-c", type=click.Path(), default="project.toml")
@click_verbosity
@click.argument("command", type=str, required=False)
@click.pass_context
def cli(ctx, config, command):
    log.debug("Loading config")
    config = get_config(config)
    command = command or config.get("default_command")

    if not command:
        log.echo("Available commands:")
        for key in config:
            if isinstance(config[key], dict):
                log.echo("\t%s", key)
        return
    log.debug("Applying overrides from options")
    apply_overrides(config[command], ctx)
    try:
        run_command(command, config)
    except ValueError as e:
        log.critical(e.args[0])
        sys.exit(2)
    except subprocess.CalledProcessError:
        log.critical("Exiting due to error in command")
        sys.exit(1)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
