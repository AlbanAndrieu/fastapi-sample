import getpass

import requests

# Your GitLab personal access token
ACCESS_TOKEN = getpass.getpass("ACCESS_TOKEN: ")

# Base URL of your GitLab instance (use 'https://gitlab.com' for GitLab.com)
GITLAB_URL = "https://gitlab.com"

# List of repository (project) IDs
project_ids = [46788175]  # Replace with your project IDs

# List of user IDs to add as guests
user_ids = [4827782, 10886450]  # Replace with your user IDs

# List of email addresses to invite
email_addresses = [
    "alban.andrieu@gmail.com",
    # "katja@philipps-byrne.com",
    # "bastian@philipps-byrne.com",
    # "chris@philipps-byrne.com",
]  # Replace with your email addresses


# List of GitLab repository URLs
repo_urls = [
    "jus-mundi-public/ds-kata-goose",
    "jusmundi-group/data-collection-structuration/scrape-unctad",
    "jusmundi-group/data-collection-structuration/scrape-wto",
    "jusmundi-group/data/citation",
    "jusmundi-group/data/citation-dataclasses",
    "jusmundi-group/data/citation-index",
    "jusmundi-group/data/citation-linking",
    "jusmundi-group/data/citation-parser",
    "jusmundi-group/data/conll-2012-corpora-creator",
    "jusmundi-group/data/feedback-analysis",
    "jusmundi-group/data/jm-beamer-template",
    "jusmundi-group/data/jm-multilabel-evaluator",
    "jusmundi-group/data/jm-ner",
    "jusmundi-group/data/jm-ner-processor",
    "jusmundi-group/data/jmhtmlparser",
    "jusmundi-group/data/jmwandb",
    "jusmundi-group/data/metadata",
    "jusmundi-group/data/prodigy-annotator",
    "jusmundi-group/data/pseudonymization",
    "jusmundi-group/data/scraper",
    "jusmundi-group/data/templates/jm-template",
    "jusmundi-group/external/one-joule",
    "jusmundi-group/full-monitoring/api",
    "jusmundi-group/infrastructure/ci-templates",
    "jusmundi-group/infrastructure/defectdojo-exporter",
    "jusmundi-group/infrastructure/docker-images/haproxy",
    "jusmundi-group/infrastructure/docker-images/headscale",
    "jusmundi-group/infrastructure/docker-images/keycloak",
    "jusmundi-group/infrastructure/docker-images/krakend",
    "jusmundi-group/infrastructure/docker-images/pgvector",
    "jusmundi-group/infrastructure/docker-images/postgres",
    "jusmundi-group/infrastructure/docker-images/traefik",
    "jusmundi-group/infrastructure/grafana-dashboards",
    "jusmundi-group/infrastructure/hashistack-cluster",
    "jusmundi-group/infrastructure/jm-computer",
    "jusmundi-group/infrastructure/openvas",
    "jusmundi-group/infrastructure/ovh-managed-pg-resource-exporter",
    "jusmundi-group/infrastructure/terraform/tf-graylog",
    "jusmundi-group/infrastructure/terraform/tf-os-instance-module",
    "jusmundi-group/infrastructure/tf-jusmundi",
    "jusmundi-group/proof-of-concept/gpt-fine-tuning",
    "jusmundi-group/proof-of-concept/jm-gtp",
    "jusmundi-group/proof-of-concept/poc-nuxt-3",
    "jusmundi-group/search-engine/api",
    "jusmundi-group/search-engine/query-translator",
    "jusmundi-group/search-engine/v2-elasticsearch",
    "jusmundi-group/technical-test/technical-test-back-dev",
    "jusmundi-group/web/abbyy-server-scripts",
    "jusmundi-group/web/analytics-processor",
    "jusmundi-group/web/back",
    "jusmundi-group/web/CommandSchedulerBundle",
    "jusmundi-group/web/conflict-checker",
    "jusmundi-group/web/docker",
    "jusmundi-group/web/e2e-tests",
    "jusmundi-group/web/entities",
    "jusmundi-group/web/front",
    "jusmundi-group/web/infrastructure",
    "jusmundi-group/web/jm-docker-compose",
    "jusmundi-group/web/jmeter",
    "jusmundi-group/web/jus-design",
    "jusmundi-group/web/keycloak-2fa-email-authenticator",
    "jusmundi-group/web/keycloak-concurrent-session",
    "jusmundi-group/web/keycloak-magic-link",
    "jusmundi-group/web/keycloak-themes",
    "jusmundi-group/web/link",
    "jusmundi-group/web/llm/assistant",
    "jusmundi-group/web/llm/assistant-bo",
    "jusmundi-group/web/llm/assistant-ocr",
    "jusmundi-group/web/llm/externalllmsdk",
    "jusmundi-group/web/llm/legal-research-assistant",
    "jusmundi-group/web/llm/qa-evaluation-framework",
    "jusmundi-group/web/locations-api-service",
    "jusmundi-group/web/nuxt",
    "jusmundi-group/web/summarizer",
    "jusmundi-group/web/templates/jm-oci/jm-go",
    "jusmundi-group/web/templates/jm-oci/jm-node",
    "jusmundi-group/web/templates/jm-oci/jm-php-fpm-apache",
    "jusmundi-group/web/templates/jm-oci/jm-python",
    "jusmundi-group/web/templates/jm-oci/jm-python-ds-serve",
    "jusmundi-group/web/templates/jm-oci/jm-ubuntu",
]  # Replace with your repository URLs


def extract_project_path(repo_url):
    # Remove the base URL part and return the project path
    project_path = repo_url.replace(f"{GITLAB_URL}/", "")
    return project_path


def get_project_id(project_path):
    url = f"{GITLAB_URL}/api/v4/projects/{project_path.replace('/', '%2F')}"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    response = requests.get(url, headers=headers, timeout=1)

    if response.status_code == 200:
        project_info = response.json()
        return project_info["id"]
    else:
        print(
            f"Failed to retrieve project ID for {project_path}: {response.status_code} - {response.json()}"
        )
        return None


def get_project_ids_from_urls(repo_urls):
    project_ids = []
    for repo_url in repo_urls:
        project_path = extract_project_path(repo_url)
        project_id = get_project_id(project_path)
        if project_id is not None:
            project_ids.append(project_id)
    return project_ids


def add_user_as_guest_to_project(project_id, user_id):
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/members"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {
        "user_id": user_id,
        "access_level": 10,  # 10 corresponds to the 'Guest' role, https://docs.gitlab.com/ee/api/member_roles.html  10 (Guest), 20 (Reporter), 30 (Developer), 40 (Maintainer), or 50 (Owner).
    }

    response = requests.post(url, headers=headers, data=data, timeout=1)

    if response.status_code == 201:
        print(f"Successfully added user {user_id} as a guest to project {project_id}")
    else:
        print(
            f"Failed to add user {user_id} to project {project_id}: {response.status_code} - {response.json()}"
        )


def invite_user_by_email_to_project(project_id, email):
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/invitations"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {
        "email": email,
        "access_level": 10,  # 10 corresponds to the 'Guest' role
    }

    response = requests.post(url, headers=headers, data=data, timeout=2)

    if response.status_code == 201:
        print(f"Successfully invited {email} as a guest to project {project_id}")
    else:
        print(
            f"Failed to invite {email} to project {project_id}: {response.status_code} - {response.json()}"
        )


def get_project_members(project_id):
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/members/all"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}

    response = requests.get(url, headers=headers, timeout=1)

    if response.status_code == 200:
        members = response.json()
        return members
    else:
        print(
            f"Failed to retrieve members for project {project_id}: {response.status_code} - {response.json()}"
        )
        return []


def display_project_members(project_id):
    members = get_project_members(project_id)
    print(f"\nMembers of project {project_id}:")
    for member in members:
        print(
            f" - {member['name']} ({member['username']}), Access Level: {member['access_level']}"
        )


def add_users_as_guests_to_projects(project_ids, user_ids, email_addresses):
    # Get project IDs from the list of repository URLs
    project_ids = project_ids + get_project_ids_from_urls(repo_urls)

    # Print the list of project IDs
    print("Project IDs:")
    for project_id in project_ids:
        print(project_id)

    for project_id in project_ids:
        for email in email_addresses:
            invite_user_by_email_to_project(project_id, email)
        for user_id in user_ids:
            add_user_as_guest_to_project(project_id, user_id)
        display_project_members(project_id)


# Add users as guests to the specified projects
add_users_as_guests_to_projects(project_ids, user_ids, email_addresses)

# python3 gitlab.py
