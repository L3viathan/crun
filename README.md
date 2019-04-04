# crun

crun (*c*‌onfig *run*‌ner) is a tool that lets you define jobs and pipelines consisting of several jobs in a config file, and then run them. Jobs can have commands associated with them, that can be run with custom options and environment variables, both of which can come either from the config file, or interactively when calling crun.

## Installation

    pip install crun

## Configuring

The configuration language is [TOML](https://github.com/toml-lang/toml), a very simple and straightforward language inspired by classic INI files. By default, `crun` looks for a file called `project.toml` in the current directory, but it can be told where to look with the `--config` switch.

Crun jobs are defined by defining toml tables (i.e. dictionaries, maps, objects):

    [step1]
    command = "echo step 1"

    [step2]
    command = "echo step 2"

Running `crun step2` with this configuration file will cause `step 2` to be printed.

## Options and the environment

Let's look at another example:

    [list]
    command = "exa"
    [list.options]
    tree = true

Calling the job `crun list` will now start exa with the `--list` switch set. If you set it to a value other than true or false, that value will be given as the value of the option, rather than treating it as a flag.

The same can be done with the `[list.environment]` table, except that it sets environment variables instead of command line switches.


## Inheritance and overriding

Until now, `crun` seems barely more useful than a shell alias or function. I hope that changes with this section.

At the top level of the configuration file, you can define meta settings. One of these is `base` which marks the config file a derivative of a different file. That way you can define jobs once, but override options in small, dependent files.

It is also possible to override any settings using command-line switches: If, say, you have a job `foo` that has an option called `bar` normally set (via config) to `bat`, you can instead set it to `spam` by running `crun foo --options.bar=spam`. This works with any and all settings of a job, so you can also override `foo.env`, for example.

## Interpolation

Sometimes, a command needs more parametrization than just options. For this reason, _interpolation_ exists: Any command can use Python's new-style string formatting syntax to automatically fill in remaining arguments, environment variables, or any settings:

    [foo]
    command = "echo {$HOME} {#1} {#2} {bar}"

Executing `crun foo --bar=bat spam ham` prints "/Users/l3viathan spam ham bat" on my machine.

***Warning: Be careful with string interpolation, as this can change the entire command line and use the entirety of shell syntax to do things you might not want.*** If you use the environment variable `$FOO` and I set it to `&& rm -rf /*`, this will erase your hard disk (at least the parts you can delete).

## Builtins

Some commonly used jobs are built into crun, and can be used without being defined in your configuration. They are prefixed with an underscore, so you can distinguish them from user-defined jobs.

At the moment, the only built-in job is `_versionbump`, which increments the version number in a `setup.py` file.
