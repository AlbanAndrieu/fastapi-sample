from nabla import __version__
from nabla.version import API_VERSION, RELEASE_VERSION, RUNTIME_VERSION


def test_version():
    assert __version__ == "1.3.7"
    assert RELEASE_VERSION == __version__
    assert API_VERSION == "v0"
    assert RUNTIME_VERSION == "v0+1.3.7"
