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
    return {
        first: second for (first, second) in pairwise(ctx.args)
    }


@click.command(
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True}
)
@click.argument("config", type=click.Path())
@click.pass_context
def cli(ctx, config):
    overrides = get_overrides(ctx)
    config = get_config(config)
    print("config:", config)
    print("extra args:", overrides)


if __name__ == "__main__":
    cli()  # pylint: disable=no-value-for-parameter
