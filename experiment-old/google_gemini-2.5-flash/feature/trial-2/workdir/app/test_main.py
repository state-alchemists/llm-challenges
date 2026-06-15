from fastapi.testclient import TestClient
from .main import app
from .database import tasks, projects, VALID_API_KEYS, initial_tasks, initial_projects
from .models import TaskStatus, TaskCreate, TaskUpdate
import pytest

client = TestClient(app)

@pytest.fixture(autouse=True)
def run_around_tests():
    # Reset the database before each test
    tasks[:] = initial_tasks
    projects[:] = initial_projects
    yield

def test_require_api_key_valid():
    response = client.get("/projects", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200

def test_require_api_key_invalid():
    response = client.get("/projects", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API Key"}

def test_require_api_key_missing():
    response = client.get("/projects")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API Key"}

def test_list_tasks_no_filters():
    response = client.get("/tasks", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == len(tasks)

def test_list_tasks_filter_status():
    response = client.get("/tasks?status=done", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "done"

def test_list_tasks_filter_priority():
    response = client.get("/tasks?priority=4", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["priority"] == 4

def test_list_tasks_filter_assigned_to():
    response = client.get("/tasks?assigned_to=bob", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["assigned_to"] == "bob"

def test_list_tasks_filter_combined():
    response = client.get("/tasks?status=todo&assigned_to=alice", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Deploy to staging"

def test_list_tasks_pagination():
    response = client.get("/tasks?page=1&page_size=2", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == 1
    assert response.json()[1]["id"] == 2

def test_list_tasks_pagination_second_page():
    response = client.get("/tasks?page=2&page_size=2", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == 3
    assert response.json()[1]["id"] == 4

def test_create_task_success():
    new_task_data = {"title": "New Task", "project_id": 1, "assigned_to": "alice"}
    response = client.post("/tasks", json=new_task_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 201
    created_task = response.json()
    assert created_task["title"] == "New Task"
    assert created_task["project_id"] == 1
    assert created_task["id"] == max([t.id for t in initial_tasks]) + 1

def test_create_task_project_not_found():
    new_task_data = {"title": "New Task", "project_id": 999}
    response = client.post("/tasks", json=new_task_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Project not found"}

def test_create_task_unauthenticated():
    new_task_data = {"title": "New Task", "project_id": 1}
    response = client.post("/tasks", json=new_task_data)
    assert response.status_code == 401

def test_update_task_success():
    task_id_to_update = 1
    update_data = {"title": "Updated Title", "status": "in_progress"}
    response = client.put(f"/tasks/{task_id_to_update}", json=update_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    updated_task = response.json()
    assert updated_task["id"] == task_id_to_update
    assert updated_task["title"] == "Updated Title"
    assert updated_task["status"] == "in_progress"

def test_update_task_not_found():
    task_id_to_update = 999
    update_data = {"title": "Updated Title"}
    response = client.put(f"/tasks/{task_id_to_update}", json=update_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

def test_update_task_unauthenticated():
    task_id_to_update = 1
    update_data = {"title": "Updated Title"}
    response = client.put(f"/tasks/{task_id_to_update}", json=update_data)
    assert response.status_code == 401

def test_delete_task_success():
    # Create a task to delete first to avoid modifying initial state directly
    create_response = client.post("/tasks", json={
        "title": "Task to Delete",
        "project_id": 1,
        "assigned_to": "bob",
    }, headers={"X-API-Key": "dev-key-alice"})
    assert create_response.status_code == 201
    task_id_to_delete = create_response.json()["id"]

    response = client.delete(f"/tasks/{task_id_to_delete}", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 204
    # Verify it's actually deleted
    get_response = client.get(f"/tasks/{task_id_to_delete}", headers={"X-API-Key": "dev-key-alice"})
    assert get_response.status_code == 404

def test_delete_task_not_found():
    task_id_to_delete = 999  # A non-existent ID
    response = client.delete(f"/tasks/{task_id_to_delete}", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404
    assert response.json() == {"detail": "Task not found"}

def test_delete_task_unauthenticated():
    task_id_to_delete = 1
    response = client.delete(f"/tasks/{task_id_to_delete}")
    assert response.status_code == 401