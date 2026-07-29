from fastapi.testclient import TestClient
import pytest
from app.main import app
from app.database import tasks, projects, VALID_API_KEYS
from app.models import TaskStatus, Task

client = TestClient(app)

def reset_database():
    # Reset in-memory database to original state for clean tests
    tasks.clear()
    tasks.extend([
        Task(id=1, title="Design schema", status=TaskStatus.done, priority=5, project_id=1, assigned_to="alice"),
        Task(id=2, title="Implement API", status=TaskStatus.in_progress, priority=4, project_id=1, assigned_to="bob"),
        Task(id=3, title="Write tests", status=TaskStatus.todo, priority=3, project_id=1),
        Task(id=4, title="Deploy to staging", status=TaskStatus.todo, priority=2, project_id=2, assigned_to="alice"),
    ])

def test_require_api_key_auth():
    reset_database()
    # When no API key is provided for a protected route, it should fail with 401.
    # Note: We need to test on a protected route once implemented, but we can check uvicorn-level/fastapi-level behavior.
    # Let's write endpoint tests that check auth first.
    pass

def test_list_projects():
    response = client.get("/projects")
    assert response.status_code == 200
    assert len(response.json()) == 2

def test_list_tasks_no_filters():
    reset_database()
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 4

def test_list_tasks_filter_status():
    reset_database()
    response = client.get("/tasks?status=todo")
    assert response.status_code == 200
    # Expected design schema and deploy are done/todo.
    # tasks 3 and 4 are todo.
    items = response.json()
    assert len(items) == 2
    for item in items:
        assert item["status"] == "todo"

def test_list_tasks_filter_priority():
    reset_database()
    response = client.get("/tasks?priority=4")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["id"] == 2

def test_list_tasks_filter_assigned_to():
    reset_database()
    response = client.get("/tasks?assigned_to=alice")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert {item["id"] for item in items} == {1, 4}

def test_list_tasks_filter_combined():
    reset_database()
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["id"] == 4

def test_list_tasks_pagination():
    reset_database()
    # page=1, page_size=2
    response = client.get("/tasks?page=1&page_size=2")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["id"] == 1
    assert items[1]["id"] == 2

    # page=2, page_size=2
    response = client.get("/tasks?page=2&page_size=2")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 2
    assert items[0]["id"] == 3
    assert items[1]["id"] == 4

    # page=3, page_size=2
    response = client.get("/tasks?page=3&page_size=2")
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 0

def test_create_task_unauthorized():
    reset_database()
    payload = {
        "title": "New Task",
        "project_id": 1
    }
    response = client.post("/tasks", json=payload)
    assert response.status_code == 401

    response = client.post("/tasks", json=payload, headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 401

def test_create_task_authorized_success():
    reset_database()
    payload = {
        "title": "New Task",
        "project_id": 1,
        "priority": 3,
        "status": "todo"
    }
    response = client.post("/tasks", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Task"
    assert data["project_id"] == 1
    assert "id" in data
    assert data["id"] > 4 # unique auto-generated int id

    # Check if indeed created in db
    assert len(tasks) == 5
    assert tasks[-1].title == "New Task"

def test_create_task_invalid_project():
    reset_database()
    payload = {
        "title": "New Task",
        "project_id": 99999
    }
    response = client.post("/tasks", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404

def test_update_task_unauthorized():
    reset_database()
    payload = {"title": "Updated Title"}
    response = client.put("/tasks/1", json=payload)
    assert response.status_code == 401

def test_update_task_success():
    reset_database()
    payload = {
        "title": "Updated Title",
        "status": "in_progress",
        "priority": 1,
        "assigned_to": "bob"
    }
    response = client.put("/tasks/1", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert data["assigned_to"] == "bob"

    # Verify state in DB
    assert tasks[0].title == "Updated Title"
    assert tasks[0].status == TaskStatus.in_progress
    assert tasks[0].priority == 1
    assert tasks[0].assigned_to == "bob"

def test_update_task_partial():
    reset_database()
    payload = {
        "status": "done"
    }
    # Before update, priority was 4, title was "Implement API"
    response = client.put("/tasks/2", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["title"] == "Implement API"
    assert data["priority"] == 4

def test_update_task_not_found():
    reset_database()
    payload = {"title": "Updated Title"}
    response = client.put("/tasks/99999", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404

def test_delete_task_unauthorized():
    reset_database()
    response = client.delete("/tasks/1")
    assert response.status_code == 401

def test_delete_task_success():
    reset_database()
    response = client.delete("/tasks/1", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    # Check deleted
    assert len(tasks) == 3
    assert not any(t.id == 1 for t in tasks)

def test_delete_task_not_found():
    reset_database()
    response = client.delete("/tasks/99999", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404
