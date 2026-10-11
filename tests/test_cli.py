import pytest

from minitela import __version__
from minitela.cli import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_args_succeeds():
    assert main([]) == 0
