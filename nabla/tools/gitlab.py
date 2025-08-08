import getpass
import os

import requests

# Your GitLab personal access token
ACCESS_TOKEN = getpass.getpass("ACCESS_TOKEN: ")

USER_EMAIL = os.environ.get("USER_EMAIL", "alban.andrieu@gmail.com")
# Base URL of your GitLab instance (use 'https://gitlab.com' for GitLab.com)
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_ACCESS_TOKEN = os.environ.get("GITLAB_ACCESS_TOKEN", "your_app_password")
GITLAB_USER = os.environ.get("GITLAB_USER", USER_EMAIL)

# List of repository (project) IDs
project_ids = [46788175]  # Replace with your project IDs

# List of user IDs to add as guests
user_ids = [4827782, 10886450]  # Replace with your user IDs

# List of email addresses to invite
email_addresses = [
    GITLAB_USER,
    # "katja@philipps-byrne.com",
    # "bastian@philipps-byrne.com",
    # "chris@philipps-byrne.com",
]  # Replace with your email addresses


# List of GitLab repository URLs
repo_urls = [
    "jus-mundi-public/<example>",
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
