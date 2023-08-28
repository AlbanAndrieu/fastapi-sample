<!-- markdown-link-check-disable-next-line -->
# [![Nabla](http://bababou.albandrieu.com/nabla/index/assets/nabla/nabla-4.png)](https://gitlab.com/AlbanAndrieu)  fastapi-sample

Fastapi sample



# Table of contents

<!-- markdown-link-check-disable -->

// spell-checker:disable

<!-- toc -->

- [Initialize](#initialize)
  * [Requirements](#requirements)
  * [Install fastapi-sample as a developer](#install-fastapi-sample-as-a-developer)
    + [Using virtualenv](#using-virtualenv)
  * [Getting started](#getting-started)
  * [Quality check](#quality-check)
  * [Add your files](#add-your-files)

<!-- tocstop -->

// spell-checker:enable

<!-- markdown-link-check-enable -->

# [Initialize](#table-of-contents)

```bash
direnv allow
pyenv install 3.8.10
pyenv local 3.8.10
python -m pipenv install --dev --ignore-pipfile
direnv allow
pre-commit install
```

## [Requirements](#table-of-contents)

  This hooks requires the following to run:

<!-- markdown-link-check-disable-next-line -->
  * [jira](https://pypi.org/project/jira/)

See requirements.txt for mandatory packages.

  This pre-commit hooks requires the following to run:

<!-- markdown-link-check-disable-next-line -->
  * [pre-commit](http://pre-commit.com)

## [Install fastapi-sample as a developer](#table-of-contents)

### Using virtualenv

Install python 3.8 and virtualenv

```bash
virtualenv --no-site-packages /opt/ansible/env38 -p python3.8
source /opt/ansible/env38/bin/activate
```

Install python 3.8 and pyenv

```bash
curl -L https://pyenv.run | bash
echo 'export PATH="~/.pyenv/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
source ~/.bashrc

pyenv install 3.8.10
```

and [integrate](https://stackabuse.com/managing-python-environments-with-direnv-and-pyenv/) it with direnv

```bash
#pip3.8 install -r hooks/requirements.txt -r requirements.testing.txt
pipenv check
python -m pipenv install --dev
python -m pipenv install --dev --ignore-pipfile
```

## [Getting started](#table-of-contents)

```bash
make up-uvicorn
```
[health](http://localhost:8080/health)

```bash
pip install -U poetry pipenv-poetry-migrate
pipenv-poetry-migrate -f Pipfile -t pyproject.toml --no-use-group-notation
```

## [Quality check](#table-of-contents)


```bash
python -m flake8  nabla --max-line-length=88 --max-complexity=30
```

[trigger error in sentry-debug](http://0.0.0.0:8080/sentry-debug)
[sentry](https://nabla-4f3768f61.sentry.io/profiling/)


## [Add your files](#table-of-contents)

- [ ] [Create](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#create-a-file) or [upload](https://docs.gitlab.com/ee/user/project/repository/web_editor.html#upload-a-file) files
- [ ] [Add files using the command line](https://docs.gitlab.com/ee/gitlab-basics/add-file.html#add-a-file-using-the-command-line) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin https://gitlab.com/AlbanAndrieu/fastapi-sample.git
git branch -M main
git push -uf origin main
```
