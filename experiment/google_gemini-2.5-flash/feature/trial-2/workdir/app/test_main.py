
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects, VALID_API_KEYS, Task, Project
from app.models import TaskStatus, TaskCreate, TaskUpdate, Task, Project

client = TestClient(app)

# Helper to get an API key for a specific user
def get_api_key(username: str):
    for key, user in VALID_API_KEYS.items():
        if user == username:
            return key
    raise ValueError(f"API key not found for user: {username}")

alice_api_key = get_api_key("alice")
bob_api_key = get_api_key("bob")
invalid_api_key = "invalid-key"

assert alice_api_key is not None, "Alice's API key not found in VALID_API_KEYS"
assert bob_api_key is not None, "Bob's API key not found in VALID_API_KEYS"


@pytest.fixture(autouse=True)
def reset_data():
    # Reset data before each test
    tasks[:] = [
        Task(id=1, title="Design schema", status=TaskStatus.done, priority=5, project_id=1, assigned_to="alice"),
        Task(id=2, title="Implement API", status=TaskStatus.in_progress, priority=4, project_id=1, assigned_to="bob"),
        Task(id=3, title="Write tests", status=TaskStatus.todo, priority=3, project_id=1),
        Task(id=4, title="Deploy to staging", status=TaskStatus.todo, priority=2, project_id=2, assigned_to="alice"),
    ]
    projects[:] = [
        Project(id=1, name="Alpha", owner="alice"),
        Project(id=2, name="Beta", owner="bob"),
    ]


# Test Authentication
def test_require_api_key_valid():
    response = client.post("/tasks", json={"title": "Test Task", "project_id": 1, "status": "todo", "priority": 1}, headers={"X-API-Key": alice_api_key})
    assert response.status_code != 401

def test_require_api_key_missing():
    response = client.post("/tasks", json={"title": "Test Task", "project_id": 1, "status": "todo", "priority": 1}, headers={})
    assert response.status_code == 401
    assert response.json() == {"detail": "X-API-Key header missing"}

def test_require_api_key_invalid():
    response = client.post("/tasks", json={"title": "Test Task", "project_id": 1, "status": "todo", "priority": 1}, headers={"X-API-Key": invalid_api_key})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}

# Test Task Filtering
def test_list_tasks_filter_by_status():
    response = client.get("/tasks?status=done")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Design schema"

def test_list_tasks_filter_by_priority():
    response = client.get("/tasks?priority=3")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Write tests"

def test_list_tasks_filter_by_assigned_to():
    response = client.get("/tasks?assigned_to=alice")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert any(task["title"] == "Design schema" for task in response.json())
    assert any(task["title"] == "Deploy to staging" for task in response.json())

def test_list_tasks_filter_combined():
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Deploy to staging"

# Test Pagination
def test_list_tasks_pagination_default():
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == 4 # All tasks fitting in default page_size

def test_list_tasks_pagination_page_2():
    # Assuming 4 tasks, page_size=2, page=2 should return tasks 2 and 3
    response = client.get("/tasks?page=2&page_size=2")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["title"] == "Write tests"
    assert response.json()[1]["title"] == "Deploy to staging"

def test_list_tasks_pagination_empty_page():
    response = client.get("/tasks?page=10&page_size=2")
    assert response.status_code == 200
    assert len(response.json()) == 0

# Test Create Task
def test_create_task_success():
    task_data = {"title": "New Task", "project_id": 1, "status": "todo", "priority": 1}
    response = client.post("/tasks", json=task_data, headers={"X-API-Key": alice_api_key})
    assert response.status_code == 201
    new_task = response.json()
    assert new_task["title"] == "New Task"
    assert new_task["id"] == 5 # Auto-generated ID

def test_create_task_project_not_found():
    task_data = {"title": "New Task", "project_id": 999, "status": "todo", "priority": 1}
    response = client.post("/tasks", json=task_data, headers={"X-API-Key": alice_api_key})
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}

def test_create_task_unauthorized():
    task_data = {"title": "New Task", "project_id": 1, "status": "todo", "priority": 1}
    response = client.post("/tasks", json=task_data, headers={})
    assert response.status_code == 401

# Test Update Task
def test_update_task_success():
    update_data = {"title": "Updated Title", "status": "done"}
    response = client.put("/tasks/1", json=update_data, headers={"X-API-Key": alice_api_key})
    assert response.status_code == 200
    updated_task = response.json()
    assert updated_task["id"] == 1
    assert updated_task["title"] == "Updated Title"
    assert updated_task["status"] == "done"

def test_update_task_not_found():
    update_data = {"title": "Updated Title"}
    response = client.put("/tasks/999", json=update_data, headers={"X-API-Key": alice_api_key})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

def test_update_task_unauthorized():
    update_data = {"title": "Updated Title"}
    response = client.put("/tasks/1", json=update_data, headers={})
    assert response.status_code == 401

# Test Delete Task
def test_delete_task_success():
    response = client.delete("/tasks/1", headers={"X-API-Key": alice_api_key})
    assert response.status_code == 204
    response = client.get("/tasks/1")
    assert response.status_code == 404

def test_delete_task_not_found():
    response = client.delete("/tasks/999", headers={"X-API-Key": alice_api_key})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

def test_delete_task_unauthorized():
    response = client.delete("/tasks/1", headers={})
    assert response.status_code == 401
