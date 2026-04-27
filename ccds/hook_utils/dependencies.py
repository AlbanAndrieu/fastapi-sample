from pathlib import Path

import tomlkit

packages = [
    "pip",
    "python-dotenv",
]

flake8_black_isort = [
    "black",
    "flake8",
    "isort",
]

ruff = ["ruff"]

basic = [
    "ipython",
    "jupyterlab",
    "matplotlib",
    "notebook",
    "numpy",
    "pandas",
    "scikit-learn",
]

scaffold = [
    "typer",
    "loguru",
    "tqdm",
]


def resolve_python_version_specifier(python_version):
    """Resolves the user-provided Python version string to a version specifier.

    Examples:

    User provides: 3.12
    Resolved version specifier: ~=3.12.0
    Compatible versions: 3.12.0, 3.12.1, 3.12.2, etc.

    User provides: 3.12.2
    Resolved version specifier: ==3.12.2
    Compatible versions: 3.12.2

    See https://packaging.python.org/en/latest/specifications/version-specifiers/#compatible-release
    """
    version_parts = python_version.split(".")
    if len(version_parts) == 2:
        major, minor = version_parts
        patch = "0"
        operator = "~="
    elif len(version_parts) == 3:
        major, minor, patch = version_parts
        operator = "=="
    else:
        raise ValueError(
            f"Invalid Python version specifier {python_version}. Please specify version as <major>.<minor> or <major>.<minor>.<patch>, e.g., 3.10, 3.10.1, etc.",
        )

    resolved_python_version = ".".join((major, minor, patch))
    return f"{operator}{resolved_python_version}"


def write_python_version(python_version):
    with open("pyproject.toml") as f:
        doc = tomlkit.parse(f.read())

    doc["project"]["requires-python"] = resolve_python_version_specifier(python_version)
    with open("pyproject.toml", "w") as f:
        f.write(tomlkit.dumps(doc))


def _generate_pixi_dependencies_config(
    packages,
    pip_only_packages,
    repo_name,
    module_name,
    python_version,
    description,
):
    """Generate pixi dependencies configuration data.

    Returns:
        tuple: (conda_dependencies, pypi_dependencies, project_config)
    """
    # Project configuration
    project_config = {
        "name": repo_name,
        "description": description or "A data science project created with cookiecutter-data-science",
        "version": "0.1.0",
        "channels": ["conda-forge"],
        "platforms": ["linux-64", "osx-64", "osx-arm64", "win-64"],
    }

    # Conda dependencies
    conda_dependencies = {"python": f"~={python_version}.0"}

    # Filter out pip and pip-only packages from conda dependencies
    conda_packages = [p for p in sorted(packages) if p not in pip_only_packages and p != "pip"]
    for p in conda_packages:
        conda_dependencies[p] = "*"

    # PyPI dependencies
    has_pip_packages = any(p in pip_only_packages for p in packages)
    pypi_dependencies = {}

    if has_pip_packages:
        # Add pip to conda dependencies when we have PyPI packages
        conda_dependencies["pip"] = "*"
        for p in sorted(packages):
            if p in pip_only_packages:
                pypi_dependencies[p] = "*"

    # Always add the module as editable PyPI dependency
    pypi_dependencies[module_name] = {"path": ".", "editable": True}

    return conda_dependencies, pypi_dependencies, project_config


def _write_requirements_txt(dependencies: str, packages) -> None:
    with Path(dependencies).open("w") as f:
        lines = sorted(packages)
        lines += ["-e ."]
        f.write("\n".join(lines))
        f.write("\n")


def _apply_pixi_to_pyproject(
    doc,
    packages,
    pip_only_packages,
    repo_name,
    module_name,
    python_version,
    description,
) -> None:
    if "tool" not in doc:
        doc["tool"] = tomlkit.table()
    if "pixi" not in doc["tool"]:
        doc["tool"]["pixi"] = tomlkit.table()

    conda_deps, pypi_deps, project_config = _generate_pixi_dependencies_config(
        packages,
        pip_only_packages,
        repo_name,
        module_name,
        python_version,
        description,
    )

    doc["tool"]["pixi"]["project"] = tomlkit.table()
    for key, value in project_config.items():
        doc["tool"]["pixi"]["project"][key] = value

    doc["tool"]["pixi"]["dependencies"] = tomlkit.table()
    for dep, version in conda_deps.items():
        doc["tool"]["pixi"]["dependencies"][dep] = version

    doc["tool"]["pixi"]["pypi-dependencies"] = tomlkit.table()
    for dep, version in pypi_deps.items():
        doc["tool"]["pixi"]["pypi-dependencies"][dep] = version


def _apply_standard_pyproject_dependencies(doc, packages, environment_manager) -> None:
    if "dependencies" not in doc["project"]:
        doc["project"].add("dependencies", sorted(packages))
        doc["project"]["dependencies"].multiline(True)
    else:
        existing_deps = set(doc["project"]["dependencies"])
        new_deps = sorted(existing_deps.union(packages))
        doc["project"]["dependencies"] = new_deps
        doc["project"]["dependencies"].multiline(True)

    if environment_manager == "poetry":
        doc["build-system"] = tomlkit.table()
        doc["build-system"]["requires"] = ["poetry-core>=2.0.0,<3.0.0"]
        doc["build-system"]["build-backend"] = "poetry.core.masonry.api"


def _write_pyproject_toml(
    dependencies: str,
    packages,
    pip_only_packages,
    environment_manager,
    repo_name,
    module_name,
    python_version,
    description,
) -> None:
    with Path(dependencies).open() as f:
        doc = tomlkit.parse(f.read())

    if environment_manager == "pixi":
        _apply_pixi_to_pyproject(
            doc,
            packages,
            pip_only_packages,
            repo_name,
            module_name,
            python_version,
            description,
        )
    else:
        _apply_standard_pyproject_dependencies(doc, packages, environment_manager)

    with Path(dependencies).open("w") as f:
        f.write(tomlkit.dumps(doc))


def _write_environment_yml(dependencies: str, packages, pip_only_packages, repo_name, python_version) -> None:
    with Path(dependencies).open("w") as f:
        lines = [
            f"name: {repo_name}",
            "channels:",
            "  - conda-forge",
            "dependencies:",
        ]
        lines += [f"  - python={python_version}"]
        lines += [f"  - {p}" for p in packages if p not in pip_only_packages]
        lines += ["  - pip:"]
        lines += [f"    - {p}" for p in packages if p in pip_only_packages]
        lines += ["    - -e ."]
        f.write("\n".join(lines))


def _write_pipfile(dependencies: str, packages, module_name, python_version) -> None:
    with Path(dependencies).open("w") as f:
        lines = ["[packages]"]
        lines += [f'{p} = "*"' for p in sorted(packages)]
        lines += [f'"{module_name}" ={{editable = true, path = "."}}']
        lines += ["", "[requires]", f'python_version = "{python_version}"']
        f.write("\n".join(lines))


def _write_pixi_toml(
    dependencies: str,
    packages,
    pip_only_packages,
    repo_name,
    module_name,
    python_version,
    description,
) -> None:
    conda_deps, pypi_deps, project_config = _generate_pixi_dependencies_config(
        packages,
        pip_only_packages,
        repo_name,
        module_name,
        python_version,
        description,
    )

    with Path(dependencies).open("w") as f:
        lines = ["[project]"]
        for key, value in project_config.items():
            if isinstance(value, str):
                lines.append(f'{key} = "{value}"')
            elif isinstance(value, list):
                lines.append(f"{key} = {value}")
            else:
                lines.append(f'{key} = "{value}"')

        lines.append("")
        lines.append("[dependencies]")
        for dep, version in conda_deps.items():
            lines.append(f'{dep} = "{version}"')

        if pypi_deps:
            lines.append("")
            lines.append("[pypi-dependencies]")
            for dep, config in pypi_deps.items():
                if isinstance(config, dict):
                    lines.append(f'{dep} = {{ path = ".", editable = true }}')
                else:
                    lines.append(f'{dep} = "{config}"')

        f.write("\n".join(lines))
        f.write("\n")


def write_dependencies(
    dependencies,
    packages,
    pip_only_packages,
    repo_name,
    module_name,
    python_version,
    environment_manager=None,
    description=None,
):
    if dependencies == "requirements.txt":
        _write_requirements_txt(dependencies, packages)
    elif dependencies == "pyproject.toml":
        _write_pyproject_toml(
            dependencies,
            packages,
            pip_only_packages,
            environment_manager,
            repo_name,
            module_name,
            python_version,
            description,
        )
    elif dependencies == "environment.yml":
        _write_environment_yml(dependencies, packages, pip_only_packages, repo_name, python_version)
    elif dependencies == "Pipfile":
        _write_pipfile(dependencies, packages, module_name, python_version)
    elif dependencies == "pixi.toml":
        _write_pixi_toml(
            dependencies,
            packages,
            pip_only_packages,
            repo_name,
            module_name,
            python_version,
            description,
        )
