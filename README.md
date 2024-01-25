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
sudo lsof -ni:8080 -sTCP:ESTABLISHED
netstat -tlnp | grep 8080
sudo lsof -i :8080
```

```bash
pip install -U poetry pipenv-poetry-migrate
pipenv-poetry-migrate -f Pipfile -t pyproject.toml --no-use-group-notation
```

## [Test JWT](#table-of-contents)

# https://jwt.io/

```bash
# go on back https://back.service.gra.dev.consul:8089/welcome
# get from cooky access_token
JWT_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJ4ZkxVNmJ4VTVDdjdjdnZpdXR4MXZEU2plSkhXRnVFbDNFaGRoVUFCbXFvIn0.eyJleHAiOjE3MDYxOTg3NDksImlhdCI6MTcwNjE5Njk0OSwiYXV0aF90aW1lIjoxNzA2MTk2OTQ4LCJqdGkiOiIyNTRlM2U5Ny02MWUxLTQ1MzgtYWQyYy04ZjRmZjBiZTJhZWIiLCJpc3MiOiJodHRwOi8va2V5Y2xvYWsuc2VydmljZS5ncmEuZGV2LmNvbnN1bC9yZWFsbXMvanVzX211bmRpIiwiYXVkIjoiYWNjb3VudCIsInN1YiI6IjJmNThhYzE2LWI3ZTItNDFjNy04ZjhkLTZiMTE5MzNlZWI2ZiIsInR5cCI6IkJlYXJlciIsImF6cCI6Imp1c211bmRpX2Rldl9iYWNrIiwic2Vzc2lvbl9zdGF0ZSI6Ijc0N2ZlMGMyLTg4NDAtNDkxMS05YmEzLTc3Y2E3YjJiNWI4YiIsImFjciI6IjEiLCJyZWFsbV9hY2Nlc3MiOnsicm9sZXMiOlsiZGVmYXVsdC1yb2xlcy1qdXNfbXVuZGkiLCJvZmZsaW5lX2FjY2VzcyIsInVtYV9hdXRob3JpemF0aW9uIl19LCJyZXNvdXJjZV9hY2Nlc3MiOnsiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJvcGVuaWQgZW1haWwgaWRfdG9rZW4gcHJvZmlsZSIsInNpZCI6Ijc0N2ZlMGMyLTg4NDAtNDkxMS05YmEzLTc3Y2E3YjJiNWI4YiIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJuYW1lIjoiQWxiYW4gQW5kcmlldSIsInByZWZlcnJlZF91c2VybmFtZSI6ImEuYW5kcmlldUBqdXNtdW5kaS5jb20iLCJnaXZlbl9uYW1lIjoiQWxiYW4iLCJmYW1pbHlfbmFtZSI6IkFuZHJpZXUiLCJlbWFpbCI6ImEuYW5kcmlldUBqdXNtdW5kaS5jb20ifQ.ZSWFSUAPybgoXvTpM6PFejxmcggtUfmDMeROip8JlAeAynGWxMFc-MNHq6rEYzlfsj-hVtV1mVNUzW39WxpsFVwicH_OskmCHY_TGnVqJptuGgOLgqDUkfaKqbyz3lx32r_NaavkcZxjxwLzLZk3OUH-it7obmjw_nqj9u6lMeBH9hlNOVOen_nUvJzNfxS9Vgs4ZEYkRIaxmIYBwYAHesTVomKfABGbHH3OsVvhujyL2yd1qD-ToPXr89vzyfQRw1LxhVtx1gP_b2MszVSRDCbkEOQaBflyssoRcF0lgTniacaRrfKdk3obiwJ0rDdcF9XQionPmEBrkUxk7Uo5wA"
curl --head -H "Authorization: Bearer $JWT_TOKEN" -X GET http://fastapi-sample.service.gra.dev.consul/
curl -verbose -I -H "X-Forwarded-For: 1.1.1.1" -H 'Content-Type: application/json' -X GET  http://fastapi-sample.service.gra.dev.consul/
```
## [Test](#table-of-contents)

# https://jwt.io/

```bash
curl -fsSL http://fastapi-sample.service.gra.dev.consul/
curl -v -I -H "X-Demo: test" -X GET  http://fastapi-sample.service.gra.dev.consul/
curl -H "X-Demo: test" -X GET http://fastapi-sample.service.gra.dev.consul/ | jq
curl -verbose -I -H "X-Forwarded-For: 1.1.1.1" -H 'Content-Type: application/json' -X GET  http://fastapi-sample.service.gra.dev.consul/
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
