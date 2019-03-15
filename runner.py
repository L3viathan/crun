import click
import toml


def pairwise(something):
    iterator = iter(something)
    yield from zip(iterator, iterator)


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
    for first, second in pairwise(ctx.args):
        assert first.startswith("--")
        set_recursive(overrides, first[2:], second)
    return overrides


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("config", type=click.Path())
@click.pass_context
def cli(ctx, config):
    config = {**get_config(config), **get_overrides(ctx)}
    print("config:", config)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
