import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects
from app.models import Task, Project, TaskStatus


@pytest.fixture(autouse=True)
def reset_db():
    # Reset tasks and projects to original state
    tasks.clear()
    tasks.extend(
        [
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
                id=3,
                title="Write tests",
                status=TaskStatus.todo,
                priority=3,
                project_id=1,
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
    )
    projects.clear()
    projects.extend(
        [
            Project(id=1, name="Alpha", owner="alice"),
            Project(id=2, name="Beta", owner="bob"),
        ]
    )


client = TestClient(app)


def test_list_tasks_no_filters():
    res = client.get("/tasks")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 4
    assert [d["id"] for d in data] == [1, 2, 3, 4]


def test_list_tasks_filter_status():
    res = client.get("/tasks?status=todo")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all(d["status"] == "todo" for d in data)


def test_list_tasks_filter_priority():
    res = client.get("/tasks?priority=4")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["id"] == 2


def test_list_tasks_filter_assigned_to():
    res = client.get("/tasks?assigned_to=alice")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert all(d["assigned_to"] == "alice" for d in data)


def test_list_tasks_combinable_filters():
    res = client.get("/tasks?status=todo&assigned_to=alice")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


def test_list_tasks_pagination_first_page():
    res = client.get("/tasks?page=1&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert [d["id"] for d in data] == [1, 2]


def test_list_tasks_pagination_second_page():
    res = client.get("/tasks?page=2&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert [d["id"] for d in data] == [3, 4]


def test_list_tasks_pagination_out_of_bounds():
    res = client.get("/tasks?page=3&page_size=2")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 0


def test_create_task_success():
    payload = {
        "title": "New Task",
        "status": "todo",
        "priority": 1,
        "project_id": 1,
        "assigned_to": "alice",
    }
    res = client.post("/tasks", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 201
    data = res.json()
    assert data["id"] == 5
    assert data["title"] == "New Task"
    assert data["project_id"] == 1
    assert data["assigned_to"] == "alice"


def test_create_task_missing_auth():
    payload = {"title": "New Task", "project_id": 1}
    res = client.post("/tasks", json=payload)
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid API Key"


def test_create_task_invalid_auth():
    payload = {"title": "New Task", "project_id": 1}
    res = client.post("/tasks", json=payload, headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid API Key"


def test_create_task_invalid_project_id():
    payload = {"title": "New Task", "project_id": 999}
    res = client.post("/tasks", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Project not found"


def test_update_task_success():
    payload = {
        "title": "Updated Design schema",
        "status": "in_progress",
        "priority": 1,
        "assigned_to": "bob",
    }
    res = client.put("/tasks/1", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 1
    assert data["title"] == "Updated Design schema"
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert data["assigned_to"] == "bob"


def test_update_task_partial():
    # Only update status
    payload = {"status": "done"}
    res = client.put("/tasks/2", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == 2
    assert data["status"] == "done"
    assert data["title"] == "Implement API"  # unchanged
    assert data["priority"] == 4  # unchanged


def test_update_task_missing_auth():
    payload = {"title": "Oops"}
    res = client.put("/tasks/1", json=payload)
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid API Key"


def test_update_task_invalid_auth():
    payload = {"title": "Oops"}
    res = client.put("/tasks/1", json=payload, headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid API Key"


def test_update_task_not_found():
    payload = {"title": "Oops"}
    res = client.put("/tasks/999", json=payload, headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Task not found"


def test_delete_task_success():
    res = client.delete("/tasks/1", headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 200
    assert res.json() == {"status": "success"}

    # Confirm it is gone
    res_get = client.get("/tasks/1")
    assert res_get.status_code == 404


def test_delete_task_missing_auth():
    res = client.delete("/tasks/1")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid API Key"


def test_delete_task_invalid_auth():
    res = client.delete("/tasks/1", headers={"X-API-Key": "wrong-key"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid API Key"


def test_delete_task_not_found():
    res = client.delete("/tasks/999", headers={"X-API-Key": "dev-key-alice"})
    assert res.status_code == 404
    assert res.json()["detail"] == "Task not found"
