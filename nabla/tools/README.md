<!-- markdown-link-check-disable-next-line -->
# [![Nabla](http://bababou.albandrieu.com/nabla/index/assets/nabla/nabla-4.png)](https://gitlab.com/jusmundi-group/proof-of-concept/fastapi-sample) fastapi-sample

Fastapi sample


# Table of contents

<!-- markdown-link-check-disable -->

// spell-checker:disable

<!-- toc -->

- [Initialize](#initialize)
- [Add user to gitlab](#add-user-to-gitlab)

<!-- tocstop -->

// spell-checker:enable

<!-- markdown-link-check-enable -->

# [Initialize](#table-of-contents)

```bash
direnv allow
pyenv install 3.10.9
pyenv local 3.10.9
python -m pipenv install --dev --ignore-pipfile
direnv allow
pre-commit install

nvm install lts/iron
```

#  Add user to gitlab

[members-api](https://docs.gitlab.com/ee/api/members.html)


[group-tech-8793233](https://gitlab.com/jusmundi-group/web)

[thien-4827782](https://gitlab.com/ThienNhatVan)

[amine-10886450](https://gitlab.com/hajali-amine)

```
curl --request DELETE --header "PRIVATE-TOKEN: ${GITLAB_FULL_PRIVATE_TOKEN}" "https://gitlab.com/api/v4/groups/8793233/billable_members/10886450"
```
