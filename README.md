<!-- markdown-link-check-disable-next-line -->
# [![Nabla](http://bababou.albandrieu.com/nabla/index/assets/nabla/nabla-4.png)](https://gitlab.com/jusmundi-group/proof-of-concept/fastapi-sample) fastapi-sample

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
  * [Test JWT](#test-jwt)
  * [Test](#test)
  * [Jupiter](#jupiter)
  * [Quality check](#quality-check)
  * [Utility scripts](#utility-scripts)
  * [Update README.md](#update-readmemd)

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
# pip3.8 install -r hooks/requirements.txt -r requirements.testing.txt
pipenv check
python -m pipenv install --dev
python -m pipenv install --dev --ignore-pipfile
```

use [poetry](https://python-poetry.org/docs/cli/)

```bash
poetry install --no-dev # --dev-only
poetry install --with dev
poetry install --extras "mysql pgsql"
#poetry install -E mysql -E pgsql
poetry install --all-extras
```

## [Getting started](#table-of-contents)

```bash
make up-uvicorn
```

[health](http://localhost:8080/health)

```bash
sudo lsof -ni:8080 -sTCP:ESTABLISHED
netstat -tlnp | grep 8080
sudo lsof -i :8080
```

```bash
pip install -U poetry pipenv-poetry-migrate
pipenv-poetry-migrate -f Pipfile -t pyproject.toml --no-use-group-notation
```

## [Test JWT](#table-of-contents)

On dev

Go on [back](https://back.service.gra.dev.consul:8089/welcome)

Get from cookie, access_token

On uat

Get the public key from [keycloak-lex](https://account-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/realms/jus_mundi) [keycloak-uat]((http://account.staging.int.jusmundi.com/realms/jus_mundi)
or [keycloak-dev](http://account.dev.int.jusmundi.com/realms/jus_mundi)
and put it to key.pem

Get the bearer [valid-jwt](https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en/api/valid-jwt)

Validate JWT [validate-jwt](https://jwt.io/)

```bash
# Go on back https://back.service.gra.dev.consul:8089/welcome
# Get from cookie access_token
#export JWT_TOKEN=$(curl -k "http://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en/api/valid-jwt")
#export JWT_TOKEN=$(curl -k "http://account.dev.int.jusmundi.com/en/api/valid-jwt")
# http://account.service.gra.dev.consul/en/api/valid-jwt
# http://keycloak-admin.service.gra.dev.consul/en/api/valid-jwt
JWT_TOKEN="eyJhbGciOiJXXXX"
curl -k --head -H "Authorization: Bearer $JWT_TOKEN" -X GET https://fastapi-sample.service.gra.dev.consul/
```

## [Test](#table-of-contents)

```bash
curl -k -fsSL https://fastapi-sample.service.gra.dev.consul/
curl -k -v -I -H "X-Demo: test" -X GET  https://fastapi-sample.service.gra.dev.consul/
curl -k -H "X-Demo: test" -X GET https://fastapi-sample.service.gra.dev.consul/ | jq
curl -k -verbose -I -H "X-Forwarded-For: 1.1.1.1" -H 'Content-Type: application/json' -X GET  http://fastapi-sample.service.gra.dev.consul/
```

[io_task][http://0.0.0.0:8080/io_task)

Result available on [pyroscope](http://localhost:4040/?query=process_cpu%3Acpu%3Ananoseconds%3Acpu%3Ananoseconds%7Bservice_name%3D%22fastapi-sample%22%7D&rightQuery=block%3Acontentions%3Acount%3A%3A%7Bservice_name%3D%22pyroscope%22%7D&leftQuery=block%3Acontentions%3Acount%3A%3A%7Bservice_name%3D%22pyroscope%22%7D&from=now-30m)

## [Jupiter](#table-of-contents)

[gitlab-data/data-science](https://gitlab.com/gitlab-data/data-science/-/tree/main?ref_type=heads)

## [Quality check](#table-of-contents)


```bash
python -m flake8  nabla --max-line-length=88 --max-complexity=30
```

[trigger error in sentry-debug](http://0.0.0.0:8080/sentry-debug)
[sentry](https://nabla-4f3768f61.sentry.io/profiling/)


## [Utility scripts](#table-of-contents)


```
python3 nabla/loki/influxdb.py

# Add header in file
# user_id,email text,last_login,cgu_read_and_accepted,roles
python3 scripts.py ~/Downloads/product-activity-2023-10-02.csv
```

## [Update README.md](#table-of-contents)


  * [github-markdown-toc](https://github.com/jonschlinkert/markdown-toc)
  * With [github-markdown-toc](https://github.com/Lucas-C/pre-commit-hooks-nodejs)

```bash
npm install -g markdown-toc
markdown-toc README.md -i
markdown-toc CHANGELOG.md -i
```
