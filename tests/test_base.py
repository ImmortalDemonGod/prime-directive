import typer
from prime_directive.bin.pd import cli


def test_cli_is_typer_app():
    assert isinstance(cli, typer.Typer)
