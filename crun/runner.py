import os
import sys
import subprocess
from pathlib import Path

import click
import toml

from .fanciness import log, click_verbosity, ColorfulCommand, color_wrap, setup
from . import builtin


class AttrDict(dict):
    def __getattr__(self, attr):
        if isinstance(self[attr], dict):
            return AttrDict(self[attr])
        return self[attr]


def recursive_merge(old, new):
    d = old.copy()
    for key in new:
        if key in d and isinstance(d[key], dict):
            d[key] = recursive_merge(d[key], new[key])
        else:
            d[key] = new[key]
    return d


def get_config(filename):
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
            message=color_wrap(
                "red", f"Configuration file {filename} not found."
            ),
        )


def make_options(ctx):
    def add_recursive(options, key, value):
        if "." in key:
            first, _, second = key.partition(".")
            add_recursive(options.setdefault(first, {}), second, value)
        else:
            options[key] = value

    options = {}

    positional = []
    remaining = list(ctx.args)
    while remaining:
        option = remaining.pop(0)
        if option == "--":
            positional.extend(remaining)
            break
        if not option.startswith("--"):  # only options are allowed
            positional.append(option)
            continue
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
    return options, positional


def get_job(config, label, dry_run=False, indent=0, parent=None):
    log.debug("Getting label %s", label, indent=indent)

    if "base" in config.get(label, ""):
        base = config[label]["base"]
        assert base in config and isinstance(
            config[base], dict
        ), "base needs to be a defined job"

        base_dict = config[base].copy()  # shallow, only for popping aliases
        base_dict.pop("alias", None)
        config[label] = recursive_merge(base_dict, config[label])

    aliases = {
        alias: label
        for label in config
        if isinstance(config[label], dict)
        for alias in config[label].get("aliases", [])
    }
    if label in aliases:
        label = aliases[label]
    if label not in config and not label.startswith("_"):
        matches = [key for key in config if key.startswith(label)]
        if len(matches) == 1:
            label = matches[0]
    if label in config:
        if "pipeline" in config[label]:
            log.debug("Making new pipeline %s", label, indent=indent)
            return Pipeline(config, label, indent, parent, dry_run)
        else:
            log.debug("Making new config job %s", label, indent=indent)
            return ConfigJob(config, label, indent, parent, dry_run)
    elif label.startswith("_"):
        log.debug("Making new builtin job %s", label, indent=indent)
        return BuiltinJob(config, label, indent, parent, dry_run)
    log.critical("No job called %s was found", label, indent=indent)
    sys.exit(3)


class Job:
    def __init__(self, config, label, indent, parent, dry_run):
        self.label = label
        self.options = {}
        self.env = {}
        self.settings = config[label] if label in config else {}
        self.config = config
        self.indent = indent
        self.parent = parent
        self.dry_run = dry_run

    @property
    def positional(self):
        if self.parent:
            return self.parent.positional
        return self._positional

    @positional.setter
    def positional(self, value):
        if self.parent:
            raise RuntimeError("Can only set positional arguments on root.")
        self._positional = value

    @property
    def global_options(self):
        if self.parent:
            return self.parent.global_options
        return self._global_options

    @global_options.setter
    def global_options(self, value):
        if self.parent:
            raise RuntimeError("Can only set global_options on root.")
        self._global_options = value

    def override_settings(self, overrides):
        def merge_settings(old, new):
            for key in new:
                if isinstance(old.get(key, None), dict):
                    merge_settings(old[key], new[key])
                else:
                    old[key] = new[key]

        log.debug(
            f"Overriding {self.label} settings with {overrides}",
            indent=self.indent,
        )

        merge_settings(self.settings, overrides)
        self.options.update(self.settings.get("options", {}))
        self.env.update(self.settings.get("environment", {}))

    @property
    def should_run(self):
        job = None
        if "run_if" in self.settings:
            job = get_job(
                self.config,
                self.settings["run_if"],
                dry_run=self.dry_run,
                indent=self.indent + 1,
                parent=self,
            )
            should_fail = False
        if "run_unless" in self.settings:
            job = get_job(
                self.config,
                self.settings["run_unless"],
                dry_run=self.dry_run,
                indent=self.indent + 1,
                parent=self,
            )
            should_fail = True
        if not job:
            return None
        log.info(
            "Checking preconditions of job %s", self.label, indent=self.indent
        )
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
    def __init__(self, config, label, indent, parent, dry_run):
        super().__init__(config, label, indent, parent, dry_run)
        self.jobs = []
        for lab in self.settings["pipeline"]:
            if lab in self.settings:
                config[lab].update(self.settings[lab])
            self.jobs.append(
                get_job(
                    config,
                    lab,
                    dry_run=dry_run,
                    indent=self.indent + 1,
                    parent=self,
                )
            )

    def execute(self):
        log.info("Running pipeline %s", self.label, indent=self.indent)
        for job in self.jobs:
            if job.label in self.settings:
                job.override_settings(self.settings[job.label])
            job.run()
        log.info("Pipeline %s finished", self.label, indent=self.indent)


class ConfigJob(Job):
    def __init__(self, config, label, indent, parent, dry_run):
        super().__init__(config, label, indent, parent, dry_run)
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
        try:
            cmd = "{}{}".format(
                self.cmd.format(
                    **AttrDict(self.settings),
                    **{f"${key}": value for key, value in self.env.items()},
                    **{
                        f"#{i+1}": value
                        for i, value in enumerate(self.positional)
                    },
                    **{"#0": " ".join(self.positional)},
                ),
                self.bake_options(),
            )
        except KeyError as e:
            log.critical(
                "Can't interpolate %s in command of job %s",
                e.args[0],
                self.label,
            )
            sys.exit(4)
        except IndexError as e:
            assert e.args[0] == "tuple index out of range"
            log.critical(
                "Broken config in job %s: Don't use {braces} that are empty or contain numbers",
                self.label,
            )
            sys.exit(5)

        log.info("Running job %s", self.label, indent=self.indent)
        try:
            if self.dry_run:
                log.info("Would run %s", cmd, indent=self.indent + 1)
            else:
                log.debug("Running command %s", cmd, indent=self.indent)
                res = subprocess.run(
                    cmd, env=self.env, shell=True, check=True, **self.sp_kwargs
                )
                self.write_output(res)
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

    @property
    def sp_kwargs(self):
        return {
            stream: subprocess.PIPE
            for stream in ["stdout", "stderr"]
            if stream in self.settings
        }

    def write_output(self, res):
        for stream in ["stdout", "stderr"]:
            filename = self.settings.get(stream)
            if not filename:
                continue
            with open(filename, "wb") as f:
                f.write(getattr(res, stream))


class BuiltinJob(Job):
    def __init__(self, config, label, indent, parent, dry_run):
        super().__init__(config, label[1:], indent, parent, dry_run)
        self.fn = getattr(builtin, label[1:])

    def execute(self):
        log.info("Running job %s", self.label, indent=self.indent)
        if self.dry_run:
            log.info("Would run builtin %s", self.label, indent=self.indent + 1)
        else:
            self.fn(
                self.label, self.options, self.settings, self.global_options
            )
        log.info("Job %s finished", self.label, indent=self.indent)


@click.command(
    cls=ColorfulCommand,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--config", "-c", type=click.Path(), default="project.toml")
@click.option(
    "--color", type=click.Choice(["always", "auto", "never"]), default="auto"
)
@click.option("--dry-run", "-n", is_flag=True)
@click_verbosity()
@click.argument("label", type=str, required=False)
@click.pass_context
def cli(ctx, config, color, dry_run, label):
    log.debug("Loading config")
    config = get_config(config)
    if "loglevel" in config:
        log.setLevel(config["loglevel"])
    setup(color, config.get("logfile"))
    log.debug("Loaded config")
    label = label or config.get("default_job")

    if not label:
        log.echo("Available jobs:")
        for key in config:
            if isinstance(config[key], dict):
                aliases = config[key].get("aliases")
                alias_str = (
                    color_wrap("gray", " ({})".format(", ".join(aliases)))
                    if aliases
                    else ""
                )
                log.echo("\t%s%s", key, alias_str)
        return
    options, positional = make_options(ctx)
    job = get_job(config, label, dry_run=dry_run)

    log.debug("Applying overrides from options")
    job.override_settings(options)
    job.global_options = options
    job.positional = positional
    try:
        if dry_run:
            log.info("Simulated execution:")
        job.run()
    except ValueError as e:
        log.critical(e.args[0])
        sys.exit(2)
    except subprocess.CalledProcessError:
        log.critical("Exiting due to error in job")
        sys.exit(1)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
