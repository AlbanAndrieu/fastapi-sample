<!-- markdown-link-check-disable-next-line -->

# [![Nabla](https://nabla.albandrieu.com/assets/nabla/nabla-4.png)](https://gitlab.com/AlbanAndrieu/fastapi-sample) fastapi-sample

Fastapi sample

# Table of contents

---

#### [Entrypoints et Dashboards (documentation dédiée)](./docs/entrypoints-and-dashboards.md)

---

<!-- markdown-link-check-disable -->

// spell-checker:disable

<!-- toc -->

- [Initialize](#initialize)
  * [Requirements](#requirements)
  * [Install fastapi-sample as a developer](#install-fastapi-sample-as-a-developer)
    + [Using virtualenv](#using-virtualenv)
    + [Using uv (recommended)](#using-uv-recommended)
  * [Getting started](#getting-started)
    + [MCP clients (e.g. OpenRAG) and A2A](#mcp-clients-eg-openrag-and-a2a)
  * [Vite UI](#vite-ui)
  * [Test JWT](#test-jwt)
  * [Test](#test)
  * [Jupiter](#jupiter)
  * [User guide](#user-guide)
    + [Installation and commands](#installation-and-commands)
    + [Database demo](#database-demo)
- [Create PostgreSQL postgres on postgres.albandrieu.com with Alembic](#create-postgresql-postgres-on-postgresalbandrieucom-with-alembic)
  * [Create PostgreSQL fastapi_sample_gitlab on postgres.albandrieu.com by hand](#create-postgresql-fastapi_sample_gitlab-on-postgresalbandrieucom-by-hand)
    + [Deploying to Vercel](#deploying-to-vercel)
    + [Temporal demo](#temporal-demo)
    + [Defect Dojo Parameters](#defect-dojo-parameters)
  * [Quality check](#quality-check)
  * [Utility scripts](#utility-scripts)
  * [Installation and commands](#installation-and-commands-1)
  * [Update README.md](#update-readmemd)
- [Monitoring & Debugging with FastAPI Radar](#monitoring--debugging-with-fastapi-radar)

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

Install python 3.12 and pyenv

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
poetry config http-basic.gitlab-ds package_read ${CI_PIP_GITLABNABLA_TOKEN}
# export POETRY_GITLAB_TOKEN_GITLAB=${GITLAB_FULL_PRIVATE_TOKEN}

poetry install --with format,test,extra,open_telemetry,api,deployment,influxdb,panda,temporal,utils,webui
poetry install --no-dev # --dev-only
poetry install --extras "mysql pgsql"
#poetry install -E mysql -E pgsql
poetry install --all-extras
```

### Using uv (recommended)

Install dependencies from the lockfile into `.venv`, then run CLI tools through `uv run` so they use that environment (avoids `ModuleNotFoundError` for packages like `pybreaker` when a global `fastapi` binary points at another Python).

```bash
uv sync
# optional: uv sync --frozen  # strict lockfile
uv run fastapi dev --port 8091
```

```bash
pytest --cov=nabla --cov-report term --cov-report xml:coverage.xml --junitxml pytest-junit.xml --no-ddtrace  --no-cov
```

### Cypher Uncypher env variable

```bash
# Cypher
# DOTENV
cp .env.secrets secrets.env.sops
sops -e -i secrets.env.sops
```

```bash
# Uncypher
# YAML
sops -d secrets-enc.yaml
# DOTENV
sops -d secrets.env.sops > .env.sops.secrets

If no mise
source .env.secrets
```

## [Getting started](#table-of-contents)

---

## Dashboards Discovery Workflow

Ce projet détecte et rend accessible automatiquement les dashboards définis dans `opencode.json` (comme FastAPI Radar).

- Tous les dashboards marqués `enabled: true` sont vérifiés et testés via `scripts/discover_dashboards.py`.
- Si un dashboard est accessible (HTTP 200 sur l'URL), un prompt permet de l’ouvrir directement dans votre navigateur !

### Usage

```bash
python scripts/discover_dashboards.py
```

### Exemple d'entrée opencode.json

```json
{
  "$schema": "https://opencode.ai/config.json",
  "command": {
    "fastapi-radar-dashboard": {
      "description": "Ouvre le dashboard radar intégré dans FastAPI",
      "url": "http://localhost:8091/__radar/",
      "enabled": true
    }
  }
}
```

---

## Monitoring & Debugging with FastAPI Radar

FastAPI Radar provides a real-time dashboard for API requests, SQL queries, exceptions, and more.

- **Dashboard URL** : [http://localhost:8091/__radar/](http://localhost:8091/__radar/)
- **API endpoints (examples)** :
    - `/__radar/api/requests` — list of recent HTTP requests
    - `/__radar/api/errors` — captured exceptions
    - `/__radar/api/stats` — global stats (requests/hour, etc)
- **Features** : Filtering, search, live updates, secure (configurable auth)
- [Full documentation → FastAPI Radar GitHub](https://github.com/doganarif/fastapi-radar)

Radar is enabled by default after install. No additional launch step is required.

---

```mermaid
sequenceDiagram
    actor User as User Client
    participant HAProxy as HAProxy
    participant Traefik as Traefik
    participant KrakenD as KrakenD
    participant API as sample API Service

    autonumber
    User ->> HAProxy: HTTP Request ( https://krakend.nabla.com/sample/threads)
    HAProxy ->> Traefik: Forward Request (Add jm-client-ip)
    Traefik ->> Traefik: Resolve (krakend.nabla.com -> kraken.service.gra.uat.consul -> IP and PORT)
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

### MCP clients (e.g. OpenRAG) and A2A

- **Outbound MCP**: set `MCP_CLIENTS` to a JSON array of stdio servers, for example:

  ```json
  [
    {
      "name": "openrag",
      "command": "uvx",
      "args": ["openrag-mcp"],
      "env": {"OPENRAG_API_KEY": "your-key", "OPENRAG_URL": "http://localhost:3000"}
    }
  ]
  ```

  With a server named `openrag`, the deep agent gains LangChain tools `openrag_search` and `openrag_chat` that call MCP tools `openrag_search` / `openrag_chat`.

- **Ops HTTP** (optional lock): set `MCP_OPS_KEY` and send header `X-MCP-Ops-Key` for `GET /v1/mcp/ops/servers`, `GET /v1/mcp/ops/servers/{name}/tools`, `POST /v1/mcp/ops/servers/{name}/call`.

- **A2A**: set `A2A_ENABLED=true` and install deps from the `api-ai` group. The app mounts JSON-RPC at `/a2a` and the agent card at `/a2a/.well-known/agent-card.json`. Set `A2A_PUBLIC_BASE_URL` so the card lists a public JSON-RPC URL (e.g. `https://api.example.com`).

[docs](http://0.0.0.0:8091/docs)
[metrics](http://0.0.0.0:8091/metrics)
[openapi](http://0.0.0.0:8091/openapi.json)
[mcp](http://0.0.0.0:8091/llm/mcp)

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

```bash
uv sync
uv run fastapi dev --port 8091
```

[health](http://localhost:8091/health)

```bash
sudo lsof -ni:8080 -sTCP:ESTABLISHED
netstat -tlnp | grep 8080
sudo lsof -i :8080
```

```bash
# Poetry migration
pip install -U poetry pipenv-poetry-migrate
pipenv-poetry-migrate -f Pipfile -t pyproject.toml --no-use-group-notation

# UV migration
uvx migrate-to-uv
```

## [Vite UI](#table-of-contents)

```bash
cd vue-client/
npm run dev
```

## [Test JWT](#table-of-contents)

Get the public key from [keycloak](https://account-ksdifu78gwc45gv1s0jshgtr764jnb79.lexsportiva.tech/realms/nabla) \[keycloak-uat\]((http://account.int.albandrieu.com/realms/nabla)

or [keycloak-dev](http://account.int.albandrieu.com/realms/nabla) [keycloak-admin](http://keycloak-admin.albandrieu.com/realms/nabla/)

and put it to key.pem

Get the bearer token [valid-jwt](https://fastapi-sample.fastapicloud.dev/en/api/valid-jwt)

Go on [back](https://back.albandrieu.com/welcome)

Get from cookie, access_token

Validate JWT [validate-jwt](https://jwt.io/)

```bash
# Go on back https://back.albandrieu.com/welcome
# Get from cookie access_token
# export JWT_TOKEN=$(curl -k "http://fastapi-sample.fastapicloud.dev/en/api/valid-jwt")
# export JWT_TOKEN=$(curl -k "https://nabla.front.albandrieu.com/en/api/valid-jwt")

# http://keycloak-admin.albandrieu.com/realms/nabla/

export JWT_TOKEN="eyJhbGcXXX"

curl -k -H "Authorization: Bearer $JWT_TOKEN" -X GET https://fastapi-sample.albandrieu.com/

# token is expired
#  {"Hello":"World"}

curl -k -i -X POST -H "Origin: https://nabla.front.albandrieu.com" \
    -H 'Content-Type: text/plain' \
    -H "Authorization: Bearer $JWT_TOKEN" \
    --data "{}" \
    "https://authorization.albandrieu.com/v1/token/upgrade"
```

## [Test](#table-of-contents)

```bash
curl -k -fsSL https://fastapi-sample.albandrieu.com/
curl -k -v -I -H "X-Demo: test" -X GET  https://fastapi-sample.albandrieu.com/
curl -k -H "X-Demo: test" -X GET https://fastapi-sample.albandrieu.com/ | jq
curl -k -verbose -I -H "X-Forwarded-For: 1.1.1.1" -H 'Content-Type: application/json' -X GET  http://fastapi-sample.albandrieu.com/
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

# Create PostgreSQL postgres on postgres.albandrieu.com with Alembic

```bash
# Create/Upgrade schema
alembic upgrade head
alembic downgrade -1
```

## Create PostgreSQL fastapi_sample_gitlab on postgres.albandrieu.com by hand

```bash
psql -h postgres.albandrieu.com -U postgres
CREATE USER fastapisample WITH PASSWORD 'XXX';
ALTER ROLE fastapisample WITH LOGIN;
CREATE USER back WITH PASSWORD 'XXX';
ALTER ROLE back WITH LOGIN;
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

### Deploying to Vercel

Deploy your project to Vercel with the following command:

```bash
npm install -g vercel
vercel --prod --archive=tgz
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

alembic upgrade head --sql > sql/schema-$(date +%F).sql

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
