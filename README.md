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
  * [Vite UI](#vite-ui)
  * [Test JWT](#test-jwt)
  * [Test](#test)
  * [Jupiter](#jupiter)
  * [User guide](#user-guide)
    + [Installation and commands](#installation-and-commands)
    + [Database demo](#database-demo)
- [Create PostgreSQL postgres on pg-gra.service.gra.dev.consul with Alembic](#create-postgresql-postgres-on-pg-graservicegradevconsul-with-alembic)
  * [Create PostgreSQL fastapi_sample_gitlab on pg-gra.service.gra.dev.consul by hand](#create-postgresql-fastapi_sample_gitlab-on-pg-graservicegradevconsul-by-hand)
    + [Temporal demo](#temporal-demo)
    + [Defect Dojo Parameters](#defect-dojo-parameters)
  * [Quality check](#quality-check)
  * [Utility scripts](#utility-scripts)
  * [Installation and commands](#installation-and-commands-1)
  * [Update README.md](#update-readmemd)

<!-- tocstop -->

// spell-checker:enable

<!-- markdown-link-check-enable -->

# [Initialize](#table-of-contents)

```bash
direnv allow
pyenv install 3.12.3
pyenv local 3.12.3
python -m pipenv install --dev --ignore-pipfile
direnv allow
pre-commit install

nvm install lts/iron
```

## [Requirements](#table-of-contents)

See requirements.txt for mandatory packages.

This pre-commit hooks requires the following to run:

<!-- markdown-link-check-disable-next-line -->

- [pre-commit](http://pre-commit.com)

## [Install fastapi-sample as a developer](#table-of-contents)

### Using virtualenv

Install python 3.10 and pyenv

```bash
curl -L https://pyenv.run | bash
echo 'export PATH="~/.pyenv/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
source ~/.bashrc

pyenv install 3.12.3
```

and [integrate](https://stackabuse.com/managing-python-environments-with-direnv-and-pyenv/) it with direnv

```bash
# pip3.10 install -r hooks/requirements.txt -r requirements.testing.txt
pipenv check
python -m pipenv install --dev
python -m pipenv install --dev --ignore-pipfile
```

use [poetry](https://python-poetry.org/docs/cli/)

```bash
poetry config http-basic.gitlab-ds package_read ${CI_PIP_GITLABJUSMUNDI_TOKEN}
# export POETRY_GITLAB_TOKEN_GITLAB=${GITLAB_FULL_PRIVATE_TOKEN}

poetry install --with format,test,extra,open_telemetry,api,deployment,influxdb,panda,temporal,utils,webui
poetry install --no-dev # --dev-only
poetry install --extras "mysql pgsql"
#poetry install -E mysql -E pgsql
poetry install --all-extras
```

```bash
pytest --cov=nabla --cov-report term --cov-report xml:coverage.xml --junitxml pytest-junit.xml --no-ddtrace  --no-cov
```

## [Getting started](#table-of-contents)

```mermaid
sequenceDiagram
    actor User as User Client
    participant HAProxy as HAProxy
    participant Traefik as Traefik
    participant KrakenD as KrakenD
    participant API as sample API Service

    autonumber
    User ->> HAProxy: HTTP Request ( https://krakend.jusmundi.com/sample/threads)
    HAProxy ->> Traefik: Forward Request (Add jm-client-ip)
    Traefik ->> Traefik: Resolve (krakend.jusmundi.com -> kraken.service.gra.uat.consul -> IP and PORT)
    Traefik ->>+ KrakenD: Forward Request (resolve kraken.service.gra.uat.consul)
    alt is jwt
    KrakenD ->> KrakenD: Check its Config (Get JWT public key URL)
    KrakenD ->> Traefik: New Request : Get JWT public key (resolve keycloak.service.gra.uat.consul)
    Traefik ->> Traefik: Resolve (keycloak.service.gra.uat.consul -> IP and PORT)
    Traefik ->>+ Keycloak: Get JWT public key
    Keycloak -->>- KrakenD: Forward Response (JWT public key)
    KrakenD ->> KrakenD: Valid Token (using JWT public key)
    end
    KrakenD ->> KrakenD: Check its config  (sample/threads -> sample.service.gra.uat.consul/threads)
    KrakenD ->>- Traefik: New Request (https://sample.service.gra.uat.consul/threads)
    Traefik ->> Traefik: Resolve (sample.service.gra.uat.consul -> IP and PORT)
    Traefik ->>+ API: Forward Request (https://sample.service.gra.uat.consul/threads)
    API -->>- KrakenD: Response (A json)
    KrakenD -->> Traefik: Forward Response
    Traefik -->> HAProxy: Forward Response
    HAProxy -->> User: HTTP Response

```

```mermaid
flowchart TD

%% Nodes
    A("fab:fa-youtube Jus AI")
    B("fa:fa-comment-dots Assistant")
    D{"fa:fa-shapes Use LRA"}
    C(fa:fa-book-open Assistant OCR)@{ shape: delay}
    H(fa:fa-code Assistant BO)@{ shape: delay}
    E(fa:fa-shapes FO)
    F("fa:fa-chevron-up SE API")
    G("fa:fa-book-open Assitant worker")
    I("fa:fa-code BACK")
    J(fa:fa-arrow-left Get documents)
    n1@{ icon: "fa:gem", pos: "b", h: 24}

%% Edge connections between nodes
    A --> B --> D & C & H
    D -- Call SE using FO --> E --> F
    D -- Call SE direclty --> F
    G -- Use AI --> B
    H -- Call --> I --> J
    F --> n1
    J --> n1

%% Individual node styling. Try the visual editor toolbar for easier styling!
    style I color:#FFFFFF, fill:#AA00FF, stroke:#AA00FF
    style B olor:#FFFFFF, stroke:#2962FF, fill:#2962FF
    style D color:#FFFFFF, stroke:#00C853, fill:#00C853
    style E color:#FFFFFF, fill:#AA00FF, stroke:#AA00FF
    style F color:#FFFFFF, fill:#AA00FF, stroke:#AA00FF
    style G color:#FFFFFF, stroke:#00C853, fill:#00C853
    style C color:#FFFFFF, stroke:#2962FF, fill:#2962FF
    style H color:#FFFFFF, stroke:#00C853, fill:#00C853

%% You can add notes with two "%" signs in a row!
```

Fix redis cluster : All slots are not covered after query all startup_nodes

```bash
sudo service redis-server start

redis-cli -c -h localhost -p 6379
localhost:6379> PING
PONG

# cluster-enabled yes
redis-cli --cluster fix 127.0.0.1:6379

# export REDIS_HOST=localhost
```

```bash
make up-uvicorn

curl --request GET http://0.0.0.0:8091/ping
curl --request GET http://0.0.0.0:8091/metrics

curl --request GET http://0.0.0.0:8091/v1/external-api
```

[docs](http://0.0.0.0:8091/docs)
[metrics](http://0.0.0.0:8091/metrics)
[openapi](http://0.0.0.0:8091/openapi.json)

```bash
export OTEL_SDK_DISABLED=true

export DD_SERVICE="fastapi-sample"
export DD_ENV="nabla"
export DD_LOGS_INJECTION=true
export DD_TRACE_SAMPLE_RATE="1"
export DD_PROFILING_ENABLED=true
export DD_APPSEC_ENABLED=true
export DD_IAST_ENABLED=true
export DD_APPSEC_SCA_ENABLED=true
export DD_GIT_COMMIT_SHA="$(git rev-parse HEAD)"
# git config --get remote.origin.url
export DD_GIT_REPOSITORY_URL="$(git config --get remote.origin.url)"

make up-gunicorn

DEBUG=1 uv run uvicorn serve:app --reload --workers 1 --host 0.0.0.0 --port 8091
```

[health](http://localhost:8091/health)

```bash
sudo lsof -ni:8080 -sTCP:ESTABLISHED
netstat -tlnp | grep 8080
sudo lsof -i :8080
```

```bash
pip install -U poetry pipenv-poetry-migrate
pipenv-poetry-migrate -f Pipfile -t pyproject.toml --no-use-group-notation
```

## [Vite UI](#table-of-contents)

```bash
cd vue-client/
npm run dev
```

## [Test JWT](#table-of-contents)

Get the public key from [keycloak-lex](https://account-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/realms/jus_mundi) \[keycloak-uat\]((http://account.staging.int.jusmundi.com/realms/jus_mundi)

or [keycloak-dev](http://account.dev.int.jusmundi.com/realms/jus_mundi) [keycloak-admin](http://keycloak-admin.service.gra.dev.consul/realms/jus_mundi/)

and put it to key.pem

Get the bearer token [valid-jwt-uat](https://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en/api/valid-jwt)

Go on [back-dev](https://back.service.gra.dev.consul/welcome)

Get from cookie, access_token

Validate JWT [validate-jwt](https://jwt.io/)

```bash
# Go on back https://back.service.gra.dev.consul/welcome
# Get from cookie access_token
# export JWT_TOKEN=$(curl -k "http://jm-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/en/api/valid-jwt")
# export JWT_TOKEN=$(curl -k "https://jm.frontnuxt.service.gra.dev.consul/en/api/valid-jwt")

# http://keycloak-admin.service.gra.dev.consul/realms/jus_mundi/

export JWT_TOKEN="eyJhbGcXXX"

curl -k -H "Authorization: Bearer $JWT_TOKEN" -X GET https://fastapi-sample.service.gra.dev.consul/

# token is expired
#  {"Hello":"World"}

curl -k -i -X POST -H "Origin: https://jm.frontnuxt.service.gra.dev.consul" \
    -H 'Content-Type: text/plain' \
    -H "Authorization: Bearer $JWT_TOKEN" \
    --data "{}" \
    "https://authorization.service.gra.dev.consul/v1/token/upgrade"
```

## [Test](#table-of-contents)

```bash
curl -k -fsSL https://fastapi-sample.service.gra.dev.consul/
curl -k -v -I -H "X-Demo: test" -X GET  https://fastapi-sample.service.gra.dev.consul/
curl -k -H "X-Demo: test" -X GET https://fastapi-sample.service.gra.dev.consul/ | jq
curl -k -verbose -I -H "X-Forwarded-For: 1.1.1.1" -H 'Content-Type: application/json' -X GET  http://fastapi-sample.service.gra.dev.consul/
```

[io_task]\[http://0.0.0.0:8080/io_task)

Result available on [pyroscope](http://localhost:4040/?query=process_cpu%3Acpu%3Ananoseconds%3Acpu%3Ananoseconds%7Bservice_name%3D%22fastapi-sample%22%7D&rightQuery=block%3Acontentions%3Acount%3A%3A%7Bservice_name%3D%22pyroscope%22%7D&leftQuery=block%3Acontentions%3Acount%3A%3A%7Bservice_name%3D%22pyroscope%22%7D&from=now-30m)

## [Jupiter](#table-of-contents)

[gitlab-data/data-science](https://gitlab.com/gitlab-data/data-science/-/tree/main?ref_type=heads)

## User guide

### Installation and commands

**Python**

```bash
python3 ./nabla/tools/get_data.py

python3 ./my-app/src/get_redis.py
```

### Database demo

# Create PostgreSQL postgres on pg-gra.service.gra.dev.consul with Alembic

```bash
# Create/Upgrade schema
alembic upgrade head
alembic downgrade -1
```

## Create PostgreSQL fastapi_sample_gitlab on pg-gra.service.gra.dev.consul by hand

```bash
psql -h pg-gra.service.gra.dev.consul -U postgres
# BW : GRADBINTEGR01 - fastapisample - dev
CREATE USER fastapisample WITH PASSWORD 'XXX';
ALTER ROLE fastapisample WITH LOGIN;
-- create database fastapi_sample_gitlab with owner fastapisample encoding 'UTF8';
create database fastapi_sample_dev with owner fastapisample encoding 'UTF8';
# ALTER USER fastapisample PASSWORD 'XXX';
GRANT ALL ON SCHEMA public TO fastapisample;
GRANT ALL ON TABLE public.note TO fastapisample;
GRANT ALL ON TABLE public.sensor_reading TO fastapisample;
GRANT ALL ON TABLE public."user" TO fastapisample;
GRANT SELECT, USAGE, UPDATE ON SEQUENCE public.sensor_reading_id_seq TO fastapisample;
-- GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.note TO fastapisample;

```

```
# for alembic
DB_USER="postgres"
DB_PASS="password-reset-XXX" # nosec
# otherwise classic connection
DB_URL="postgresql://postgres:password-reset-XXX@127.0.0.1:5432/fastapi_sample_dev" # nosec
# Remove asyncpg for alembic to be able to init DB as fastapisample
DB_URL="postgresql://fastapisample:password-reset-XXX@127.0.0.1:5432/fastapi_sample_dev" # nosec
```

### Temporal demo

[Temporal](https://github.com/temporalio/samples-python/tree/main)

```
poetry install --with format,test,extra,open_telemetry,api,deployment,influxdb,panda,temporal,utils,webui
poetry run python nabla/temporalio/activities.py

poetry run python worker.py
poetry run python starter.py

```

### Defect Dojo Parameters

[dd_product](http://defectdojo.service.gra.uat.consul/api/v2/products/)

[dd_product_types](http://defectdojo.service.gra.uat.consul/api/v2/product_types/)

All parameters need to be provided as environment variables:

| Parameter                           | Re-import findings | Import languages | Remark                                                                                            |
| ----------------------------------- | :----------------: | :--------------: | ------------------------------------------------------------------------------------------------- |
| DD_URL                              |     Mandatory      |    Mandatory     | Base URL of the DefectDojo instance                                                               |
| DD_API_KEY                          |     Mandatory      |    Mandatory     | Shall be defined as a secret, eg. a protected variable in GitLab or an encrypted secret in GitHub |
| DD_PRODUCT_TYPE_NAME                |     Mandatory      |    Mandatory     | If a product type with this name does not exist, it will be created                               |
| DD_PRODUCT_NAME                     |     Mandatory      |    Mandatory     | If a product with this name does not exist, it will be created                                    |
| DD_ENGAGEMENT_NAME                  |     Mandatory      |        -         | If an engagement with this name does not exist for the given product, it will be created          |
| DD_ENGAGEMENT_TARGET_START          |      Optional      |        -         | Format: YYYY-MM-DD, default: `today`. The target start date for a newly created engagement.       |
| DD_ENGAGEMENT_TARGET_END            |      Optional      |        -         | Format: YYYY-MM-DD, default: `2999-12-31`. The target start date for a newly created engagement.  |
| DD_TEST_NAME                        |     Mandatory      |        -         | If a test with this name does not exist for the given engagement, it will be created              |
| DD_TEST_TYPE_NAME                   |     Mandatory      |        -         | From DefectDojo's list of test types, eg. `Trivy Scan`                                            |
| DD_FILE_NAME                        |      Optional      |    Mandatory     |                                                                                                   |
| DD_ACTIVE                           |      Optional      |        -         | Default: `true`                                                                                   |
| DD_VERIFIED                         |      Optional      |        -         | Default: `true`                                                                                   |
| DD_MINIMUM_SEVERITY                 |      Optional      |        -         |                                                                                                   |
| DD_GROUP_BY                         |      Optional      |        -         | Group by file path, component name, component name + version                                      |
| DD_PUSH_TO_JIRA                     |      Optional      |        -         | Default: `false`                                                                                  |
| DD_CLOSE_OLD_FINDINGS               |      Optional      |        -         | Default: `true`                                                                                   |
| DD_CLOSE_OLD_FINDINGS_PRODUCT_SCOPE |      Optional      |        -         | Default: `false`                                                                                  |
| DD_DO_NOT_REACTIVATE                |      Optional      |        -         | Default: `false`                                                                                  |
| DD_VERSION                          |      Optional      |        -         |                                                                                                   |
| DD_ENDPOINT_ID                      |      Optional      |        -         |                                                                                                   |
| DD_SERVICE                          |      Optional      |        -         |                                                                                                   |
| DD_BUILD_ID                         |      Optional      |        -         |                                                                                                   |
| DD_COMMIT_HASH                      |      Optional      |        -         |                                                                                                   |
| DD_BRANCH_TAG                       |      Optional      |        -         |                                                                                                   |
| DD_API_SCAN_CONFIGURATION_ID        |      Optional      |        -         | Id of the API scan configuration for API based parsers, e.g. SonarQube                            |
| DD_SOURCE_CODE_MANAGEMENT_URI       |      Optional      |        -         |                                                                                                   |
| DD_SSL_VERIFY                       |      Optional      |     Optional     | Disable SSL verification by setting to `false` or `0`. Default: `true`                            |
| DD_EXTRA_HEADER_1                   |      Optional      |     Optional     | If extra header key is needed for auth in wafs or similar                                         |
| DD_EXTRA_HEADER_1_VALUE             |      Optional      |     Optional     | The corresponding value for extra header key                                                      |
| DD_EXTRA_HEADER_2                   |      Optional      |     Optional     | If extra header key is needed for auth in wafs or similar                                         |
| DD_EXTRA_HEADER_2_VALUE             |      Optional      |     Optional     | The corresponding value for extra header key                                                      |

## [Quality check](#table-of-contents)

```bash
python -m flake8  nabla --max-line-length=88 --max-complexity=30

ruff check --output-format gitlab > report_ruff.json && ruff format --check

pyright --outputjson > report_raw.json
pyright-to-gitlab-ci --src report_raw.json --output report_pyright.json --base_path .
```

[trigger error in sentry-debug](http://0.0.0.0:8080/sentry-debug)
[sentry](https://nabla-4f3768f61.sentry.io/profiling/)

## [Utility scripts](#table-of-contents)

```
python3 nabla/loki/influxdb.py

# Create/Upgrade schema
alembic upgrade head

# Add header in file
# user_id,email text,last_login,cgu_read_and_accepted,roles
python3 scripts.py ~/Downloads/product-activity-2023-10-02.csv
```

## Installation and commands

**GO**npm run dev

```bash
go version
go mod init example.com/m/v2
go mod tidy
go run hello-world.go
go build hello-world.go
ls
./hello-world
```

## [Update README.md](#table-of-contents)

- [github-markdown-toc](https://github.com/jonschlinkert/markdown-toc)
- With [github-markdown-toc](https://github.com/Lucas-C/pre-commit-hooks-nodejs)

```bash
npm install -g markdown-toc
markdown-toc README.md -i
markdown-toc CHANGELOG.md -i
```
