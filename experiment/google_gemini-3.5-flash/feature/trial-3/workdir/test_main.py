import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models import TaskStatus

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_db():
    from app import database
    from app.models import Task, Project, TaskStatus
    database.tasks.clear()
    database.tasks.extend([
        Task(id=1, title="Design schema", status=TaskStatus.done, priority=5, project_id=1, assigned_to="alice"),
        Task(id=2, title="Implement API", status=TaskStatus.in_progress, priority=4, project_id=1, assigned_to="bob"),
        Task(id=3, title="Write tests", status=TaskStatus.todo, priority=3, project_id=1),
        Task(id=4, title="Deploy to staging", status=TaskStatus.todo, priority=2, project_id=2, assigned_to="alice"),
    ])
    database.projects.clear()
    database.projects.extend([
        Project(id=1, name="Alpha", owner="alice"),
        Project(id=2, name="Beta", owner="bob"),
    ])


def test_list_projects():
    response = client.get("/projects")
    assert response.status_code == 200
    assert len(response.json()) == 2


# 1. Authentication Tests
def test_auth_missing_header():
    # POST, PUT, DELETE should fail with 401 without X-API-Key
    response = client.post("/tasks", json={"title": "Test Task", "project_id": 1})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API Key"

    response = client.put("/tasks/1", json={"title": "Updated"})
    assert response.status_code == 401

    response = client.delete("/tasks/1")
    assert response.status_code == 401


def test_auth_invalid_key():
    headers = {"X-API-Key": "invalid-key"}
    response = client.post("/tasks", json={"title": "Test Task", "project_id": 1}, headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API Key"


def test_auth_valid_key():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.post("/tasks", json={"title": "Test Task", "project_id": 1}, headers=headers)
    assert response.status_code == 201


# 2. Task Filtering Tests
def test_filter_tasks_by_status():
    response = client.get("/tasks?status=todo")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(task["status"] == "todo" for task in data)


def test_filter_tasks_by_priority():
    response = client.get("/tasks?priority=4")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["priority"] == 4


def test_filter_tasks_by_assigned_to():
    response = client.get("/tasks?assigned_to=bob")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["assigned_to"] == "bob"


def test_filter_tasks_combined():
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["title"] == "Deploy to staging"


# 3. Pagination Tests
def test_pagination_defaults():
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 4  # all 4 tasks within default page_size 20


def test_pagination_slice():
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
        "title": "New Task",
        "status": "in_progress",
        "priority": 1,
        "project_id": 2,
        "assigned_to": "bob"
    }
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 5  # max existing is 4, so next is 5
    assert data["title"] == "New Task"
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert data["project_id"] == 2
    assert data["assigned_to"] == "bob"

    # Verify persistent in database list
    get_response = client.get("/tasks/5")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "New Task"


def test_create_task_missing_project():
    headers = {"X-API-Key": "dev-key-alice"}
    payload = {
        "title": "New Task",
        "project_id": 999
    }
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


# 5. Update Task Tests
def test_update_task_partial():
    headers = {"X-API-Key": "dev-key-bob"}
    payload = {
        "status": "done",
        "assigned_to": "alice"
    }
    response = client.put("/tasks/2", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["assigned_to"] == "alice"
    # priority and title should remain unchanged
    assert data["priority"] == 4
    assert data["title"] == "Implement API"


def test_update_task_not_found():
    headers = {"X-API-Key": "dev-key-bob"}
    response = client.put("/tasks/999", json={"title": "Does not exist"}, headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"


# 6. Delete Task Tests
def test_delete_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.delete("/tasks/3", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"detail": "Task deleted"}

    # Verify gone from /tasks/{task_id}
    get_response = client.get("/tasks/3")
    assert get_response.status_code == 404


def test_delete_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.delete("/tasks/999", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Task not found"
