from setuptools import setup
import versioneer

setup(
    name="nabla",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description="Nabla",
    url="url",
    author="author",
    author_email="email",
    zip_safe=True,
    packages=["nabla"],
    # package_dir={"": "src"},
    scripts=["bin/rundemo"],
)
