from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects, VALID_API_KEYS
from app.models import TaskStatus, Task

client = TestClient(app)


def test_require_api_key_valid():
    response = client.get("/projects", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200


def test_require_api_key_invalid():
    response = client.get("/projects", headers={"X-API-Key": "invalid-key"})
    assert response.status_code == 401


def test_require_api_key_missing():
    response = client.get("/projects")
    assert response.status_code == 401


def test_list_tasks_no_filters():
    response = client.get("/tasks")
    assert response.status_code == 200
    assert len(response.json()) == len(tasks)


def test_list_tasks_filter_by_status():
    response = client.get(f"/tasks?status={TaskStatus.in_progress.value}")
    assert response.status_code == 200
    filtered_tasks = [task for task in tasks if task.status == TaskStatus.in_progress]
    assert len(response.json()) == len(filtered_tasks)
    assert all(task["status"] == TaskStatus.in_progress.value for task in response.json())


def test_list_tasks_filter_by_priority():
    response = client.get("/tasks?priority=5")
    assert response.status_code == 200
    filtered_tasks = [task for task in tasks if task.priority == 5]
    assert len(response.json()) == len(filtered_tasks)
    assert all(task["priority"] == 5 for task in response.json())


def test_list_tasks_filter_by_assigned_to():
    response = client.get("/tasks?assigned_to=bob")
    assert response.status_code == 200
    filtered_tasks = [task for task in tasks if task.assigned_to == "bob"]
    assert len(response.json()) == len(filtered_tasks)
    assert all(task["assigned_to"] == "bob" for task in response.json())


def test_list_tasks_combined_filters():
    response = client.get(f"/tasks?status={TaskStatus.todo.value}&priority=3&assigned_to=None")
    assert response.status_code == 200
    filtered_tasks = [task for task in tasks if task.status == TaskStatus.todo and task.priority == 3 and task.assigned_to is None]
    assert len(response.json()) == len(filtered_tasks)


def test_list_tasks_pagination():
    response = client.get("/tasks?page=1&page_size=2")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == tasks[0].id
    assert response.json()[1]["id"] == tasks[1].id


def test_list_tasks_pagination_second_page():
    response = client.get("/tasks?page=2&page_size=2")
    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.json()[0]["id"] == tasks[2].id
    assert response.json()[1]["id"] == tasks[3].id


def test_create_task_success():
    task_data = {"title": "New Task", "project_id": 1, "status": "todo", "priority": 1, "assigned_to": "alice"}
    response = client.post("/tasks", json=task_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 201
    created_task = response.json()
    assert created_task["title"] == "New Task"
    assert created_task["project_id"] == 1
    assert created_task["id"] == max([t.id for t in tasks]) # Check if ID is correctly auto-generated


def test_create_task_unauthorized():
    task_data = {"title": "Unauthorized Task", "project_id": 1}
    response = client.post("/tasks", json=task_data)
    assert response.status_code == 401


def test_create_task_project_not_found():
    task_data = {"title": "Task for non-existent project", "project_id": 999}
    response = client.post("/tasks", json=task_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404


def test_update_task_success():
    task_id_to_update = tasks[0].id
    update_data = {"title": "Updated Title", "status": "done"}
    response = client.put(f"/tasks/{task_id_to_update}", json=update_data, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 200
    updated_task = response.json()
    assert updated_task["title"] == "Updated Title"
    assert updated_task["status"] == "done"
    # Verify it's actually updated in the in-memory database
    assert next(t for t in tasks if t.id == task_id_to_update).title == "Updated Title"


def test_update_task_not_found():
    response = client.put("/tasks/999", json={"title": "Non Existent"}, headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404


def test_update_task_unauthorized():
    task_id_to_update = tasks[0].id
    update_data = {"title": "Unauthorized Update"}
    response = client.put(f"/tasks/{task_id_to_update}", json=update_data)
    assert response.status_code == 401


def test_delete_task_success():
    task_id_to_delete = tasks[0].id
    response = client.delete(f"/tasks/{task_id_to_delete}", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 204
    # Verify it's actually deleted from the in-memory database
    assert not any(t.id == task_id_to_delete for t in tasks)


def test_delete_task_not_found():
    response = client.delete("/tasks/999", headers={"X-API-Key": "dev-key-alice"})
    assert response.status_code == 404


def test_delete_task_unauthorized():
    task_id_to_delete = tasks[0].id
    response = client.delete(f"/tasks/{task_id_to_delete}")
    assert response.status_code == 401