import re

from nabla import __version__


def test_version():
    # assert __version__ == '1.1.0'
    assert re.match(r"^1.1.0.+$", __version__)  # nosec
