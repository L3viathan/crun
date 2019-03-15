from itertools import zip_longest
import click
import toml


def get_config(filename):
    with open(filename) as f:
        data = toml.load(f)
        if "base" in data:
            data = {**get_config(data["base"]), **data}
    return data


def get_overrides(ctx):
    def set_recursive(store, dotted_name, value):
        head, _, tail = dotted_name.partition(".")
        if tail:
            store.setdefault(head, {})
            set_recursive(store[head], tail, value)
        else:
            store[head] = value

    overrides = {}
    remaining = iter(ctx.args)
    for option in remaining:
        assert option.startswith("--")  # only options are allowed
        if "=" in option:
            option, value = option.split("=", maxsplit=1)
        else:
            value = next(remaining)
        set_recursive(overrides, option[2:], value)
    return overrides


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("config", type=click.Path())
@click.pass_context
def cli(ctx, config):
    config = {**get_config(config), **get_overrides(ctx)}
    print("config:", config)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
