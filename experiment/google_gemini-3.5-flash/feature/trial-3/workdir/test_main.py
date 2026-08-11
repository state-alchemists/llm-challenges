import pytest
import copy
from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    original_tasks = copy.deepcopy(tasks)
    original_projects = copy.deepcopy(projects)
    yield
    tasks.clear()
    tasks.extend(original_tasks)
    projects.clear()
    projects.extend(original_projects)


# 1. Test existing routes
def test_list_projects():
    response = client.get("/projects")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha"


def test_list_tasks_no_filters():
    response = client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert data[0]["title"] == "Design schema"


def test_get_task():
    response = client.get("/tasks/1")
    assert response.status_code == 200
    assert response.json()["title"] == "Design schema"

    response = client.get("/tasks/999")
    assert response.status_code == 404


# 2. Test Task Filtering
def test_list_tasks_filter_status():
    response = client.get("/tasks?status=todo")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(item["status"] == "todo" for item in data)


def test_list_tasks_filter_priority():
    response = client.get("/tasks?priority=4")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2


def test_list_tasks_filter_assigned_to():
    response = client.get("/tasks?assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(item["assigned_to"] == "alice" for item in data)


def test_list_tasks_multiple_filters():
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


# 3. Test Pagination
def test_list_tasks_pagination():
    # Total tasks is 4. Page 1, page_size 2
    response = client.get("/tasks?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2

    # Page 2, page_size 2
    response = client.get("/tasks?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 3
    assert data[1]["id"] == 4

    # Page 3, page_size 2 (out of bounds/empty)
    response = client.get("/tasks?page=3&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


def test_list_tasks_filter_and_pagination():
    # Only 2 tasks have status="todo" (id 3 and 4)
    # Page 1, page_size 1 should return only id 3
    response = client.get("/tasks?status=todo&page=1&page_size=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 3

    # Page 2, page_size 1 should return only id 4
    response = client.get("/tasks?status=todo&page=2&page_size=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


# 4. Test Create Task
def test_create_task_unauthenticated():
    response = client.post("/tasks", json={"title": "New Task", "project_id": 1})
    assert response.status_code == 401


def test_create_task_invalid_auth():
    response = client.post(
        "/tasks",
        json={"title": "New Task", "project_id": 1},
        headers={"X-API-Key": "invalid-key"},
    )
    assert response.status_code == 401


def test_create_task_invalid_project():
    response = client.post(
        "/tasks",
        json={"title": "New Task", "project_id": 999},
        headers={"X-API-Key": "dev-key-alice"},
    )
    assert response.status_code == 404
    assert "Project not found" in response.json()["detail"]


def test_create_task_success():
    payload = {
        "title": "New Task",
        "status": "todo",
        "priority": 3,
        "project_id": 1,
        "assigned_to": "bob",
    }
    response = client.post(
        "/tasks", json=payload, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response.status_code in (200, 201)
    data = response.json()
    assert data["id"] == 5
    assert data["title"] == "New Task"
    assert data["project_id"] == 1
    assert data["assigned_to"] == "bob"

    # Verify it exists in tasks list now
    get_response = client.get("/tasks/5")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "New Task"


# 5. Test Update Task
def test_update_task_unauthenticated():
    response = client.put("/tasks/1", json={"status": "in_progress"})
    assert response.status_code == 401


def test_update_task_invalid_auth():
    response = client.put(
        "/tasks/1", json={"status": "in_progress"}, headers={"X-API-Key": "invalid-key"}
    )
    assert response.status_code == 401


def test_update_task_not_found():
    response = client.put(
        "/tasks/999",
        json={"status": "in_progress"},
        headers={"X-API-Key": "dev-key-alice"},
    )
    assert response.status_code == 404


def test_update_task_success():
    response = client.put(
        "/tasks/1",
        json={
            "status": "in_progress",
            "title": "Updated Schema",
            "priority": 1,
            "assigned_to": "bob",
        },
        headers={"X-API-Key": "dev-key-alice"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["title"] == "Updated Schema"
    assert data["priority"] == 1
    assert data["assigned_to"] == "bob"

    # Verify partial update (only status)
    response = client.put(
        "/tasks/2", json={"status": "done"}, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["title"] == "Implement API"  # remained unchanged


# 6. Test Delete Task
def test_delete_task_unauthenticated():
    response = client.delete("/tasks/1")
    assert response.status_code == 401


def test_delete_task_invalid_auth():
    response = client.delete("/tasks/1", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401


def test_delete_task_not_found():
    response = client.delete("/tasks/999", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404


def test_delete_task_success():
    response = client.delete("/tasks/1", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code in (200, 204)  # 204 or 200 is acceptable

    # Verify it is deleted
    get_response = client.get("/tasks/1")
    assert get_response.status_code == 404
