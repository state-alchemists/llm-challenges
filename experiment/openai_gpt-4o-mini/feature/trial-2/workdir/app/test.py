import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from .main import app

client = TestClient(app)

VALID_API_KEYS = {"dev-key-alice": "alice", "dev-key-bob": "bob"}


@pytest.fixture
def valid_api_key():
    return next(iter(VALID_API_KEYS.keys()))


def test_create_task(valid_api_key):
    response = client.post(
        "/tasks",
        json={"title": "New Task", "status": "todo", "priority": 1, "project_id": 1},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New Task"


def test_update_task(valid_api_key):
    # Assume task with ID 1 exists
    response = client.put(
        "/tasks/1",
        json={"title": "Updated Task"},
        headers={"X-API-Key": valid_api_key},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Task"


def test_delete_task(valid_api_key):
    # Assume task with ID 1 exists
    response = client.delete("/tasks/1", headers={"X-API-Key": valid_api_key})
    assert response.status_code == 200


def test_list_tasks(valid_api_key):
    response = client.get("/tasks?status=todo", headers={"X-API-Key": valid_api_key})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_paginated_tasks(valid_api_key):
    response = client.get("/tasks?page=1&page_size=2", headers={"X-API-Key": valid_api_key})
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) <= 2
