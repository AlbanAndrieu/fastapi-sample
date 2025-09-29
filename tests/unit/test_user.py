"""Test the API."""

import pytest
from fastapi.testclient import TestClient

from server import app


@pytest.fixture(scope="module")
def test_app():
	client = TestClient(app)
	yield client  # testing happens here


def test_user_current(test_app) -> None:
	"""It runs and gives correct response for users."""

	expected_status: int = 200

	# with pytest.raises(AssertionError):
	response = test_app.get("/test/users/current")

	# then
	print(response.json())
	assert response.status_code == expected_status
	assert response.json() == {
		"name": "Alban Andrieu",
		"password": "XXX",
		"email": "alban.andrieu@gmail.com",
		"phone": "0695435353",
		"address": "11 terrasse de l'université",
		"city": "Paris",
		"state": "FR",
		"zipcode": "92000",
		"country": "France",
	}

def test_users(test_app) -> None:
	"""It runs and gives correct response for users."""

	expected_status: int = 422

	# with pytest.raises(AssertionError):
	response = test_app.get("/test/users/0")

	# then
	assert response.status_code == expected_status
	assert response.json() == {'detail': [{'type': 'missing', 'loc': ['query', 'current_user'], 'msg': 'Field required', 'input': None}]}


def test_user_me(test_app) -> None:
	"""It runs and gives correct response for user me."""

	expected_status: int = 404

	response = test_app.get("https://jusmundi.com/api/user/me")

	assert response.status_code == expected_status
	# assert response.json() == {
	#     "name": "User 0",
	#     "email": "alban.andrieu@gmail.com",
	# }
