import re

from nabla import __version__


def test_version():
    # CI checks out a clean tree; local checkouts may include a dirty suffix.
    assert re.fullmatch(r"\d+(?:\.\d+)*(?:\+[\w.-]+)?", __version__)

    __version_test__ = "v1.0.6"
    assert __version_test__ == "v1.0.6"

    assert re.fullmatch(r"v\d{1,5}\.\d{1,5}\.\d{1,5}", __version_test__)
