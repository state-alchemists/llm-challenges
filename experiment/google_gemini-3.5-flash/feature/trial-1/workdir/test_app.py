import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import Task, Project, TaskStatus
import app.database as db

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_database():
    # Store initial tasks and projects
    db.projects.clear()
    db.projects.extend([
        Project(id=1, name="Alpha", owner="alice"),
        Project(id=2, name="Beta", owner="bob"),
    ])
    db.tasks.clear()
    db.tasks.extend([
        Task(id=1, title="Design schema", status=TaskStatus.done, priority=5, project_id=1, assigned_to="alice"),
        Task(id=2, title="Implement API", status=TaskStatus.in_progress, priority=4, project_id=1, assigned_to="bob"),
        Task(id=3, title="Write tests", status=TaskStatus.todo, priority=3, project_id=1),
        Task(id=4, title="Deploy to staging", status=TaskStatus.todo, priority=2, project_id=2, assigned_to="alice"),
    ])
    yield


# 1. Authentication Tests
def test_auth_success():
    # GET /projects doesn't require auth but let's test a POST with auth
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.post(
        "/tasks",
        json={"title": "New Task", "project_id": 1},
        headers=headers
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New Task"

def test_auth_missing_or_invalid():
    # POST without key
    response = client.post("/tasks", json={"title": "New Task", "project_id": 1})
    assert response.status_code == 401
    
    # POST with invalid key
    response = client.post(
        "/tasks",
        json={"title": "New Task", "project_id": 1},
        headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


# 2. Filtering Tests
def test_filter_by_status():
    response = client.get("/tasks?status=todo")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(task["status"] == "todo" for task in data)

def test_filter_by_priority():
    response = client.get("/tasks?priority=4")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2

def test_filter_by_assigned_to():
    response = client.get("/tasks?assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(task["assigned_to"] == "alice" for task in data)

def test_filter_combined():
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


# 3. Pagination Tests
def test_pagination_default():
    # Default is page 1, size 20, returning all 4
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 4

def test_pagination_custom_slices():
    response = client.get("/tasks?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2

    response = client.get("/tasks?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 3
    assert data[1]["id"] == 4

    response = client.get("/tasks?page=3&page_size=2")
    assert response.status_code == 200
    assert len(response.json()) == 0


# 4. Create Task Tests
def test_create_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    payload = {
        "title": "Build UI",
        "status": "todo",
        "priority": 1,
        "project_id": 2,
        "assigned_to": "alice"
    }
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 5
    assert data["title"] == "Build UI"
    assert data["status"] == "todo"
    assert data["priority"] == 1
    assert data["project_id"] == 2
    assert data["assigned_to"] == "alice"

def test_create_task_missing_project_id():
    headers = {"X-API-Key": "dev-key-alice"}
    payload = {
        "title": "Build UI",
        "project_id": 999
    }
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


# 5. Update Task Tests
def test_update_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    payload = {
        "title": "Design revised schema",
        "status": "in_progress",
        "priority": 1,
        "assigned_to": "bob"
    }
    response = client.put("/tasks/1", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Design revised schema"
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert data["assigned_to"] == "bob"

def test_update_task_partial():
    headers = {"X-API-Key": "dev-key-bob"}
    payload = {
        "status": "done"
    }
    response = client.put("/tasks/3", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 3
    assert data["status"] == "done"
    # priority and title should remain unchanged
    assert data["title"] == "Write tests"
    assert data["priority"] == 3

def test_update_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.put("/tasks/999", json={"status": "done"}, headers=headers)
    assert response.status_code == 404


# 6. Delete Task Tests
def test_delete_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.delete("/tasks/1", headers=headers)
    assert response.status_code == 200
    assert response.json()["detail"] == "Task deleted"

    # Confirm deleted
    response = client.get("/tasks/1")
    assert response.status_code == 404

def test_delete_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.delete("/tasks/999", headers=headers)
    assert response.status_code == 404
