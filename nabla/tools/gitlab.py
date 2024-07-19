import getpass

import requests

# Your GitLab personal access token
ACCESS_TOKEN = getpass.getpass("ACCESS_TOKEN: ")

# Base URL of your GitLab instance (use 'https://gitlab.com' for GitLab.com)
GITLAB_URL = "https://gitlab.com"

# List of repository (project) IDs
project_ids = [46788175]  # Replace with your project IDs

# List of user IDs to add as guests
user_ids = [4827782]  # Replace with your user IDs 20730529, 20166973


def add_user_as_guest_to_project(project_id, user_id):
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/members"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    data = {
        "user_id": user_id,
        "access_level": 10,  # 10 corresponds to the 'Guest' role
    }

    response = requests.post(url, headers=headers, data=data, timeout=1)

    if response.status_code == 201:
        print(f"Successfully added user {user_id} as a guest to project {project_id}")
    else:
        print(
            f"Failed to add user {user_id} to project {project_id}: {response.status_code} - {response.json()}"
        )


def add_users_as_guests_to_projects(project_ids, user_ids):
    for project_id in project_ids:
        for user_id in user_ids:
            add_user_as_guest_to_project(project_id, user_id)


# Add users as guests to the specified projects
add_users_as_guests_to_projects(project_ids, user_ids)

# python3 gitlab.py
