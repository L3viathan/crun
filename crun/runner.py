import os
import sys
import subprocess
import click
import toml
import colorful

from .fanciness import log, click_verbosity, ColorfulCommand
from . import builtin


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


def make_options(ctx):
    def add_recursive(options, key, value):
        if "." in key:
            first, _, second = key.partition(".")
            add_recursive(options.setdefault(first, {}), second, value)
        else:
            options[key] = value

    options = {}

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

        add_recursive(options, option[2:], value)
    return options


def get_job(config, label):
    log.debug("Getting label %s", label)
    if label in config:
        if "pipeline" in config[label]:
            log.debug("Making new pipeline %s", label)
            return Pipeline(config, label)
        else:
            log.debug("Making new config job %s", label)
            return ConfigJob(config, label)
    elif label.startswith("_"):
        log.debug("Making new builtin job %s", label)
        return BuiltinJob(config, label)
    log.critical("No job called %s was found", label)
    sys.exit(3)


class Job:
    def __init__(self, config, label):
        self.label = label
        self.options = {}
        self.env = {}
        self.global_options = {}
        self.settings = config[label] if label in config else {}

    def override_settings(self, overrides):
        log.debug(f"Overriding {self.label} settings with {overrides}")
        def merge_settings(old, new):
            for key in new:
                if isinstance(old.get(key, None), dict):
                    merge_settings(old[key], new[key])
                else:
                    old[key] = new[key]
        merge_settings(self.settings, overrides)
        self.options.update(self.settings.get("options", {}))
        self.env.update(self.settings.get("environment", {}))


class Pipeline(Job):
    def __init__(self, config, label):
        super().__init__(config, label)
        self.jobs = []
        for lab in self.settings["pipeline"]:
            if lab in self.settings:
                config[lab].update(self.settings[lab])
            self.jobs.append(get_job(config, lab))

    def run(self):
        log.info("Running pipeline %s", self.label)
        for job in self.jobs:
            if job.label in self.settings:
                job.override_settings(self.settings[job.label])
            job.global_options = self.global_options
            job.run()


class ConfigJob(Job):
    def __init__(self, config, label):
        super().__init__(config, label)
        self.cmd = self.settings["command"]
        self.options = {
            key: val for key, val in self.settings.get("options", {}).items()
        }
        self.env = os.environ.copy()
        self.env.update(
            {
                key: val
                for key, val in self.settings.get("environment", {}).items()
            }
        )

    def bake_options(self):
        if self.options:
            return " {}".format(
                " ".join(
                    (f"--{key}" if val is True else f"--{key}={val}")
                    for (key, val) in self.options.items()
                    if val is not False
                )
            )
        else:
            return ""

    def run(self):
        cmd = "{}{}".format(self.cmd, self.bake_options())
        log.info("Running job %s", self.label)
        try:
            subprocess.run(cmd, env=self.env, shell=True, check=True)
            return log.info("Job %s finished", self.label)
        except subprocess.CalledProcessError as e:
            if self.settings.get("fail_ok", False):
                return log.info("Job %s finished", self.label)
            log.error(
                "Job %s returned with non-zero exit code %s",
                self.label,
                e.returncode,
            )
            raise e


class BuiltinJob(Job):
    def __init__(self, config, label):
        super().__init__(config, label[1:])
        self.fn = getattr(builtin, label[1:])

    def run(self):
        self.fn(self.label, self.options, self.settings, self.global_options)


@click.command(
    cls=ColorfulCommand,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--config", "-c", type=click.Path(), default="project.toml")
@click_verbosity
@click.argument("label", type=str, required=False)
@click.pass_context
def cli(ctx, config, label):
    log.debug("Loading config")
    config = get_config(config)
    label = label or config.get("default_job")

    if not label:
        log.echo("Available jobs:")
        for key in config:
            if isinstance(config[key], dict):
                log.echo("\t%s", key)
        return
    options = make_options(ctx)
    job = get_job(config, label)

    log.debug("Applying overrides from options")
    job.override_settings(options)
    job.global_options = options
    try:
        job.run()
    except ValueError as e:
        log.critical(e.args[0])
        sys.exit(2)
    except subprocess.CalledProcessError:
        log.critical("Exiting due to error in job")
        sys.exit(1)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
