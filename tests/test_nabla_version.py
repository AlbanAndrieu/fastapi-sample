from nabla import __version__
from nabla.version import API_VERSION, RELEASE_VERSION, RUNTIME_VERSION


def test_version():
    assert RELEASE_VERSION == __version__
    assert API_VERSION == "v0"
    assert RUNTIME_VERSION == f"{API_VERSION}+{__version__}"
