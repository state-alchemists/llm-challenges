from fastapi.testclient import TestClient
from .main import app
from .database import tasks, projects

client = TestClient(app)


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


def test_list_tasks_filter_status():
    response = client.get("/tasks?status=todo")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for t in data:
        assert t["status"] == "todo"


def test_list_tasks_filter_priority():
    response = client.get("/tasks?priority=4")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2


def test_list_tasks_filter_assigned_to():
    response = client.get("/tasks?assigned_to=bob")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["assigned_to"] == "bob"


def test_list_tasks_combined_filters():
    response = client.get("/tasks?status=todo&assigned_to=alice")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


def test_list_tasks_pagination():
    # page 1, page_size 2 -> should return first 2 tasks (id=1, id=2)
    response = client.get("/tasks?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 1
    assert data[1]["id"] == 2

    # page 2, page_size 2 -> should return next 2 tasks (id=3, id=4)
    response = client.get("/tasks?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["id"] == 3
    assert data[1]["id"] == 4


def test_require_api_key_auth_failures():
    # POST, PUT, DELETE should fail with 401 if API key is missing or invalid
    for method in ["post", "put", "delete"]:
        url = "/tasks" if method == "post" else "/tasks/1"
        kwargs = {"json": {}} if method != "delete" else {}
        
        # Missing header
        fn = getattr(client, method)
        response = fn(url, **kwargs)
        assert response.status_code == 401
        assert "missing" in response.json()["detail"].lower()

        # Invalid API key
        response = fn(url, headers={"X-API-Key": "fake-key"}, **kwargs)
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()


def test_create_task():
    # Valid creation
    payload = {
        "title": "New Integration Task",
        "status": "todo",
        "priority": 1,
        "project_id": 2,
        "assigned_to": "bob"
    }
    response = client.post(
        "/tasks",
        headers={"X-API-Key": "dev-key-alice"},
        json=payload
    )
    assert response.status_code == 201
    data = response.json()
    assert data["id"] == 5
    assert data["title"] == "New Integration Task"
    assert data["priority"] == 1
    assert data["project_id"] == 2
    assert data["assigned_to"] == "bob"

    # Verify task was added
    response = client.get("/tasks/5")
    assert response.status_code == 200
    assert response.json()["title"] == "New Integration Task"


def test_create_task_invalid_project():
    payload = {
        "title": "Invalid Project Task",
        "project_id": 999
    }
    response = client.post(
        "/tasks",
        headers={"X-API-Key": "dev-key-alice"},
        json=payload
    )
    assert response.status_code == 404
    assert "project" in response.json()["detail"].lower()


def test_update_task():
    # Partially update task with ID 2
    payload = {
        "title": "Implement API (Optimized)",
        "priority": 5,
        "assigned_to": "alice"
    }
    response = client.put(
        "/tasks/2",
        headers={"X-API-Key": "dev-key-bob"},
        json=payload
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 2
    assert data["title"] == "Implement API (Optimized)"
    assert data["priority"] == 5
    assert data["assigned_to"] == "alice"
    # status should remain unchanged (in_progress)
    assert data["status"] == "in_progress"


def test_update_task_not_found():
    payload = {"title": "Ghost Task"}
    response = client.put(
        "/tasks/999",
        headers={"X-API-Key": "dev-key-bob"},
        json=payload
    )
    assert response.status_code == 404


def test_delete_task():
    # Delete task with ID 3 (which was "Write tests")
    response = client.delete(
        "/tasks/3",
        headers={"X-API-Key": "dev-key-bob"}
    )
    assert response.status_code == 200
    assert "deleted" in response.json()["detail"].lower()

    # Get should now return 404
    response = client.get("/tasks/3")
    assert response.status_code == 404


def test_delete_task_not_found():
    response = client.delete(
        "/tasks/999",
        headers={"X-API-Key": "dev-key-bob"}
    )
    assert response.status_code == 404
