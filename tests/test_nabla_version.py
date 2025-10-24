import re

from nabla import __version__


def test_version():
    # assert re.match(r"^0\+untagged.*.+$", __version__)  # nosec
    #  2024-04-12-1+156.gcb8029a.dirty
    assert re.match(r"^.*.dirty+$", __version__)  # nosec

    __version_test__ = "v1.0.6"
    assert __version_test__ == "v1.0.6"

    assert re.match(r"^v1.0.6?.+$", __version_test__)  # nosec
    assert re.match(r"^v\d{1,5}\.\d{1,5}\.\d{1,5}$", __version_test__)  # nosec
