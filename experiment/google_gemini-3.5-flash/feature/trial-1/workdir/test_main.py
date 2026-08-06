import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects
from app.models import Task, Project, TaskStatus

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database():
    initial_projects = [
        Project(id=1, name="Alpha", owner="alice"),
        Project(id=2, name="Beta", owner="bob"),
    ]
    initial_tasks = [
        Task(
            id=1,
            title="Design schema",
            status=TaskStatus.done,
            priority=5,
            project_id=1,
            assigned_to="alice",
        ),
        Task(
            id=2,
            title="Implement API",
            status=TaskStatus.in_progress,
            priority=4,
            project_id=1,
            assigned_to="bob",
        ),
        Task(
            id=3, title="Write tests", status=TaskStatus.todo, priority=3, project_id=1
        ),
        Task(
            id=4,
            title="Deploy to staging",
            status=TaskStatus.todo,
            priority=2,
            project_id=2,
            assigned_to="alice",
        ),
    ]
    projects.clear()
    projects.extend(initial_projects)
    tasks.clear()
    tasks.extend(initial_tasks)


def test_require_api_key():
    # POST, PUT, DELETE require API key
    # No API Key provided
    response = client.post("/tasks", json={"title": "New Task", "project_id": 1})
    assert response.status_code == 401
    assert "Invalid API Key" in response.json()["detail"]

    # Invalid API Key provided
    response = client.post(
        "/tasks",
        json={"title": "New Task", "project_id": 1},
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401
    assert "Invalid API Key" in response.json()["detail"]

    # Valid API Key provided (alice)
    response = client.post(
        "/tasks",
        json={"title": "New Task", "project_id": 1},
        headers={"X-API-Key": "dev-key-alice"},
    )
    assert response.status_code == 201


def test_get_tasks_filtering():
    # Filter by status
    response = client.get("/tasks", params={"status": "todo"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(t["status"] == "todo" for t in data)

    # Filter by priority
    response = client.get("/tasks", params={"priority": 4})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2

    # Filter by assigned_to
    response = client.get("/tasks", params={"assigned_to": "alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(t["assigned_to"] == "alice" for t in data)

    # Combinable filters
    response = client.get("/tasks", params={"status": "todo", "assigned_to": "alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


def test_get_tasks_pagination():
    # Check default pagination: page_size = 20, should return all 4
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 4

    # page_size = 2, page = 1
    response = client.get("/tasks", params={"page": 1, "page_size": 2})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2

    # page_size = 2, page = 2
    response = client.get("/tasks", params={"page": 2, "page_size": 2})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 3
    assert data[1]["id"] == 4

    # page_size = 2, page = 3
    response = client.get("/tasks", params={"page": 3, "page_size": 2})
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_create_task_endpoint():
    # Valid creation
    payload = {
        "title": "Build UI",
        "status": "todo",
        "priority": 1,
        "project_id": 2,
        "assigned_to": "bob",
    }
    response = client.post(
        "/tasks", json=payload, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 5
    assert data["title"] == "Build UI"
    assert data["project_id"] == 2
    assert data["assigned_to"] == "bob"

    # Verify ID is unique/incremented
    payload2 = {"title": "Next Task", "project_id": 1}
    response2 = client.post(
        "/tasks", json=payload2, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response2.status_code == 201
    assert response2.json()["id"] == 6

    # Non-existent project
    payload_bad = {"title": "Bad Task", "project_id": 999}
    response_bad = client.post(
        "/tasks", json=payload_bad, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response_bad.status_code == 404
    assert response_bad.json()["detail"] == "Project not found"


def test_update_task_endpoint():
    # Partial update: title and status
    payload = {"title": "Updated Schema Design", "status": "in_progress"}
    response = client.put(
        "/tasks/1", json=payload, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["title"] == "Updated Schema Design"
    assert data["status"] == "in_progress"
    assert data["priority"] == 5  # Unchanged
    assert data["assigned_to"] == "alice"  # Unchanged

    # Update assigned_to to null or different user
    response2 = client.put(
        "/tasks/1", json={"assigned_to": "bob"}, headers={"X-API-Key": "dev-key-alice"}
    )
    assert response2.status_code == 200
    assert response2.json()["assigned_to"] == "bob"

    # Non-existent task
    response_bad = client.put(
        "/tasks/999",
        json={"title": "Doesn't exist"},
        headers={"X-API-Key": "dev-key-alice"},
    )
    assert response_bad.status_code == 404
    assert response_bad.json()["detail"] == "Task not found"


def test_delete_task_endpoint():
    # Delete existing task
    response = client.delete("/tasks/3", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert response.json()["id"] == 3

    # Subsequent GET on deleted task should be 404
    response_get = client.get("/tasks/3")
    assert response_get.status_code == 404

    # Non-existent task delete
    response_bad = client.delete("/tasks/999", headers={"X-API-Key": "dev-key-alice"})
    assert response_bad.status_code == 404
    assert response_bad.json()["detail"] == "Task not found"
