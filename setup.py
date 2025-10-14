# pylint: skip-file
from setuptools import find_packages
from setuptools import setup
import versioneer

# read the contents of your README file
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="nabla",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    packages=find_packages(),
    scripts=["bin/rundemo"],
    author="Alban Andrieu",
    author_email="alban.andrieu@free.fr",
    description="Nabla",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="url",
    zip_safe=True,
)
