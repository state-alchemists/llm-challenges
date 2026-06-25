import pytest
from fastapi.testclient import TestClient
from .main import app

client = TestClient(app)
VALID_API_KEYS = {"dev-key-alice": "alice", "dev-key-bob": "bob"}


def test_create_task():
    response = client.post("/tasks", json={"title": "New Task", "project_id": 1}, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert response.json()["title"] == "New Task"


def test_get_tasks():
    response = client.get("/tasks", headers={"X-API-Key": "dev-key-bob"})
    assert response.status_code == 200


def test_get_task():
    response = client.get("/tasks/1", headers={"X-API-Key": "dev-key-bob"})
    assert response.status_code == 200
    assert response.json()["id"] == 1


def test_update_task():
    response = client.put("/tasks/1", json={"title": "Updated Task"}, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Task"


def test_delete_task():
    response = client.delete("/tasks/1", headers={"X-API-Key": "dev-key-bob"})
    assert response.status_code == 200