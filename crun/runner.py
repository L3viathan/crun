import os
import sys
import subprocess
from pathlib import Path

import click
import toml
import colorful

from .fanciness import log, click_verbosity, ColorfulCommand
from . import builtin


def get_config(filename):
    def recursive_merge(old, new):
        d = old.copy()
        for key in new:
            if key in d and isinstance(d[key], dict):
                d[key] = recursive_merge(d[key], new[key])
            else:
                d[key] = new[key]
        return d

    cwd = Path.cwd()
    while not (cwd / filename).exists():
        if cwd.parent == cwd:
            break  # stop at the root
        cwd = cwd.parent
    try:
        with open(cwd / filename) as f:
            data = toml.load(f)
            if "base" in data:
                data = recursive_merge(
                    get_config((cwd / filename).parent / data["base"]), data
                )
            os.chdir((cwd / filename).parent)
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


def get_job(config, label, indent=0):
    log.debug("Getting label %s", label, indent=indent)
    aliases = {
        alias: label
        for label in config
        if isinstance(config[label], dict)
        for alias in config[label].get("aliases", [])
    }
    if label in aliases:
        label = aliases[label]
    if label in config:
        if "pipeline" in config[label]:
            log.debug("Making new pipeline %s", label, indent=indent)
            return Pipeline(config, label, indent)
        else:
            log.debug("Making new config job %s", label, indent=indent)
            return ConfigJob(config, label, indent)
    elif label.startswith("_"):
        log.debug("Making new builtin job %s", label, indent=indent)
        return BuiltinJob(config, label, indent)
    log.critical("No job called %s was found", label, indent=indent)
    sys.exit(3)


class Job:
    def __init__(self, config, label, indent):
        self.label = label
        self.options = {}
        self.env = {}
        self.global_options = {}
        self.settings = config[label] if label in config else {}
        self.config = config
        self.indent = indent

    def override_settings(self, overrides):
        log.debug(
            f"Overriding {self.label} settings with {overrides}",
            indent=self.indent,
        )

        def merge_settings(old, new):
            for key in new:
                if isinstance(old.get(key, None), dict):
                    merge_settings(old[key], new[key])
                else:
                    old[key] = new[key]

        merge_settings(self.settings, overrides)
        self.options.update(self.settings.get("options", {}))
        self.env.update(self.settings.get("environment", {}))

    @property
    def should_run(self):
        job = None
        if "run_if" in self.settings:
            job = get_job(self.config, self.settings["run_if"], self.indent + 1)
            should_fail = False
        if "run_unless" in self.settings:
            job = get_job(
                self.config, self.settings["run_unless"], self.indent + 1
            )
            should_fail = True
        if not job:
            return None
        log.info("Checking preconditions of job %s", self.label, indent=self.indent)
        try:
            job.run()
        except subprocess.CalledProcessError:
            return should_fail
        return not should_fail

    def run(self):
        precondition = self.should_run
        if precondition is False:
            log.info(
                "Skipping job %s due to precondition",
                self.label,
                indent=self.indent,
            )
        else:
            self.execute()

    def execute(self):
        raise NotImplementedError()


class Pipeline(Job):
    def __init__(self, config, label, indent):
        super().__init__(config, label, indent)
        self.jobs = []
        for lab in self.settings["pipeline"]:
            if lab in self.settings:
                config[lab].update(self.settings[lab])
            self.jobs.append(get_job(config, lab, self.indent + 1))

    def execute(self):
        log.info("Running pipeline %s", self.label, indent=self.indent)
        for job in self.jobs:
            if job.label in self.settings:
                job.override_settings(self.settings[job.label])
            job.global_options = self.global_options
            job.run()
        log.info("Pipeline %s finished", self.label, indent=self.indent)


class ConfigJob(Job):
    def __init__(self, config, label, indent):
        super().__init__(config, label, indent)
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

    def execute(self):
        cmd = "{}{}".format(self.cmd, self.bake_options())
        log.info("Running job %s", self.label, indent=self.indent)
        try:
            subprocess.run(cmd, env=self.env, shell=True, check=True)
            return log.info("Job %s finished", self.label, indent=self.indent)
        except subprocess.CalledProcessError as e:
            if self.settings.get("fail_ok", False):
                return log.info(
                    "Job %s finished", self.label, indent=self.indent
                )
            log.error(
                "Job %s returned with non-zero exit code %s",
                self.label,
                e.returncode,
                indent=self.indent,
            )
            raise e


class BuiltinJob(Job):
    def __init__(self, config, label, indent):
        super().__init__(config, label[1:], indent)
        self.fn = getattr(builtin, label[1:])

    def execute(self):
        log.info("Running job %s", self.label, indent=self.indent)
        self.fn(self.label, self.options, self.settings, self.global_options)
        log.info("Job %s finished", self.label, indent=self.indent)


@click.command(
    cls=ColorfulCommand,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--config", "-c", type=click.Path(), default="project.toml")
@click_verbosity()
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
