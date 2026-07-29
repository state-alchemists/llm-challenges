import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects
from app.models import Task, TaskStatus, Project

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    tasks.clear()
    tasks.extend([
        Task(id=1, title="Design schema", status=TaskStatus.done, priority=5, project_id=1, assigned_to="alice"),
        Task(id=2, title="Implement API", status=TaskStatus.in_progress, priority=4, project_id=1, assigned_to="bob"),
        Task(id=3, title="Write tests", status=TaskStatus.todo, priority=3, project_id=1),
        Task(id=4, title="Deploy to staging", status=TaskStatus.todo, priority=2, project_id=2, assigned_to="alice"),
    ])
    projects.clear()
    projects.extend([
        Project(id=1, name="Alpha", owner="alice"),
        Project(id=2, name="Beta", owner="bob"),
    ])


# 1. Authentication Tests
def test_auth_missing_header():
    response = client.post("/tasks", json={
        "title": "New Task",
        "project_id": 1
    })
    assert response.status_code == 401
    assert "detail" in response.json()


def test_auth_invalid_key():
    response = client.post(
        "/tasks",
        headers={"X-API-Key": "invalid-key"},
        json={
            "title": "New Task",
            "project_id": 1
        }
    )
    assert response.status_code == 401


def test_auth_valid_key_success():
    response = client.post(
        "/tasks",
        headers={"X-API-Key": "dev-key-alice"},
        json={
            "title": "New Task",
            "project_id": 1
        }
    )
    assert response.status_code == 200
    assert response.json()["title"] == "New Task"


# 2. Task Filtering Tests
def test_filter_by_status():
    response = client.get("/tasks?status=done")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1


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
    assert {t["id"] for t in data} == {1, 4}


def test_filter_combinable():
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


# 3. Pagination Tests
def test_pagination_defaults():
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4  # all fits in page size 20


def test_pagination_slices():
    response = client.get("/tasks?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert [t["id"] for t in data] == [1, 2]

    response_page2 = client.get("/tasks?page=2&page_size=2")
    assert response_page2.status_code == 200
    data2 = response_page2.json()
    assert len(data2) == 2
    assert [t["id"] for t in data2] == [3, 4]


# 4. Create Task Tests
def test_create_task_project_not_found():
    response = client.post(
        "/tasks",
        headers={"X-API-Key": "dev-key-alice"},
        json={
            "title": "Invalid Project Task",
            "project_id": 999
        }
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_create_task_auto_generated_id():
    response = client.post(
        "/tasks",
        headers={"X-API-Key": "dev-key-alice"},
        json={
            "title": "Automated Testing",
            "project_id": 1,
            "status": "in_progress",
            "priority": 1,
            "assigned_to": "alice"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 5
    assert data["title"] == "Automated Testing"
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert data["assigned_to"] == "alice"


# 5. Update Task Tests
def test_update_task_not_found():
    response = client.put(
        "/tasks/999",
        headers={"X-API-Key": "dev-key-alice"},
        json={"title": "Updated Title"}
    )
    assert response.status_code == 404


def test_update_task_partial_success():
    response = client.put(
        "/tasks/3",
        headers={"X-API-Key": "dev-key-alice"},
        json={
            "status": "in_progress",
            "assigned_to": "bob"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 3
    assert data["title"] == "Write tests"  # unchanged
    assert data["status"] == "in_progress"
    assert data["assigned_to"] == "bob"


# 6. Delete Task Tests
def test_delete_task_not_found():
    response = client.delete(
        "/tasks/999",
        headers={"X-API-Key": "dev-key-alice"}
    )
    assert response.status_code == 404


def test_delete_task_success():
    response = client.delete(
        "/tasks/3",
        headers={"X-API-Key": "dev-key-alice"}
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Task deleted"

    # Verify get_task returns 404 now
    response_get = client.get("/tasks/3")
    assert response_get.status_code == 404
