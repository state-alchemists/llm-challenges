import pytest
from fastapi.testclient import TestClient
from app.main import app
import app.database as db
from app.models import Task, TaskStatus, Project

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    # Save original tasks and projects
    orig_tasks = [
        task.model_copy() if hasattr(task, "model_copy") else task.copy()
        for task in db.tasks
    ]
    orig_projects = [
        proj.model_copy() if hasattr(proj, "model_copy") else proj.copy()
        for proj in db.projects
    ]
    yield
    # Restore original tasks and projects
    db.tasks.clear()
    db.tasks.extend(orig_tasks)
    db.projects.clear()
    db.projects.extend(orig_projects)


def test_list_projects():
    response = client.get("/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha"
    assert data[1]["name"] == "Beta"


def test_list_tasks_no_filters():
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2


def test_list_tasks_filter_status():
    response = client.get("/tasks", params={"status": "todo"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for task in data:
        assert task["status"] == "todo"


def test_list_tasks_filter_priority():
    response = client.get("/tasks", params={"priority": 4})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2
    assert data[0]["priority"] == 4


def test_list_tasks_filter_assigned_to():
    response = client.get("/tasks", params={"assigned_to": "alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for task in data:
        assert task["assigned_to"] == "alice"


def test_list_tasks_combinable_filters():
    response = client.get("/tasks", params={"status": "todo", "assigned_to": "alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4
    assert data[0]["status"] == "todo"
    assert data[0]["assigned_to"] == "alice"


def test_list_tasks_pagination():
    # Page 1, Page size 2 -> should return tasks 1 and 2
    response = client.get("/tasks", params={"page": 1, "page_size": 2})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2

    # Page 2, Page size 2 -> should return tasks 3 and 4
    response = client.get("/tasks", params={"page": 2, "page_size": 2})
    assert response.status_code == 200
    data2 = response.json()
    assert len(data2) == 2
    assert data2[0]["id"] == 3
    assert data2[1]["id"] == 4


def test_auth_missing_header():
    # POST /tasks
    response = client.post("/tasks", json={"title": "New Task", "project_id": 1})
    assert response.status_code == 401
    assert "detail" in response.json()

    # PUT /tasks/1
    response = client.put("/tasks/1", json={"title": "Updated Task"})
    assert response.status_code == 401

    # DELETE /tasks/1
    response = client.delete("/tasks/1")
    assert response.status_code == 401


def test_auth_invalid_header():
    headers = {"X-API-Key": "invalid-key"}

    # POST /tasks
    response = client.post("/tasks", json={"title": "New Task", "project_id": 1}, headers=headers)
    assert response.status_code == 401

    # PUT /tasks/1
    response = client.put("/tasks/1", json={"title": "Updated Task"}, headers=headers)
    assert response.status_code == 401

    # DELETE /tasks/1
    response = client.delete("/tasks/1", headers=headers)
    assert response.status_code == 401


def test_create_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    task_data = {
        "title": "Build UI component",
        "status": "todo",
        "priority": 1,
        "project_id": 1,
        "assigned_to": "alice",
    }
    response = client.post("/tasks", json=task_data, headers=headers)
    assert response.status_code == 200
    created_task = response.json()
    assert created_task["id"] == 5
    assert created_task["title"] == "Build UI component"
    assert created_task["status"] == "todo"
    assert created_task["priority"] == 1
    assert created_task["project_id"] == 1
    assert created_task["assigned_to"] == "alice"

    # Verify it is in database
    get_res = client.get("/tasks/5")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Build UI component"


def test_create_task_project_not_found():
    headers = {"X-API-Key": "dev-key-bob"}
    task_data = {
        "title": "Invalid project task",
        "project_id": 999,
    }
    response = client.post("/tasks", json=task_data, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_update_task_partial_success():
    headers = {"X-API-Key": "dev-key-alice"}
    # Check current status
    orig_response = client.get("/tasks/2")
    assert orig_response.json()["title"] == "Implement API"
    assert orig_response.json()["status"] == "in_progress"

    # Partially update
    update_data = {
        "status": "done",
    }
    response = client.put("/tasks/2", json=update_data, headers=headers)
    assert response.status_code == 200
    updated = response.json()
    assert updated["title"] == "Implement API"  # unchanged
    assert updated["status"] == "done"  # changed

    # Verify in DB
    get_res = client.get("/tasks/2")
    assert get_res.json()["status"] == "done"


def test_update_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.put("/tasks/999", json={"title": "Updated"}, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


def test_delete_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    # Verify task exists
    assert client.get("/tasks/3").status_code == 200

    # Delete
    response = client.delete("/tasks/3", headers=headers)
    assert response.status_code == 200
    assert response.json()["detail"] == "Task deleted"

    # Verify no longer exists
    assert client.get("/tasks/3").status_code == 404


def test_delete_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.delete("/tasks/999", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"
