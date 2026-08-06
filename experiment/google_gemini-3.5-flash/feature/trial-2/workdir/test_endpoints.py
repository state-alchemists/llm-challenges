from fastapi.testclient import TestClient
from app.main import app

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


def test_list_tasks_status_filter():
    response = client.get("/tasks", params={"status": "todo"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(task["status"] == "todo" for task in data)


def test_list_tasks_priority_filter():
    response = client.get("/tasks", params={"priority": 4})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 2


def test_list_tasks_assigned_to_filter():
    response = client.get("/tasks", params={"assigned_to": "alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(task["assigned_to"] == "alice" for task in data)


def test_list_tasks_combined_filters():
    response = client.get("/tasks", params={"status": "todo", "assigned_to": "alice"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 4


def test_list_tasks_pagination():
    # First page with size 2
    response1 = client.get("/tasks", params={"page": 1, "page_size": 2})
    assert response1.status_code == 200
    data1 = response1.json()
    assert len(data1) == 2
    assert data1[0]["id"] == 1
    assert data1[1]["id"] == 2

    # Second page with size 2
    response2 = client.get("/tasks", params={"page": 2, "page_size": 2})
    assert response2.status_code == 200
    data2 = response2.json()
    assert len(data2) == 2
    assert data2[0]["id"] == 3
    assert data2[1]["id"] == 4


def test_auth_missing_header():
    # POST, PUT, DELETE should fail with 401 if header is missing
    response_post = client.post("/tasks", json={"title": "Test", "project_id": 1})
    assert response_post.status_code == 401

    response_put = client.put("/tasks/1", json={"title": "Updated"})
    assert response_put.status_code == 401

    response_delete = client.delete("/tasks/1")
    assert response_delete.status_code == 401


def test_auth_invalid_key():
    headers = {"X-API-Key": "invalid-key"}
    response_post = client.post(
        "/tasks", json={"title": "Test", "project_id": 1}, headers=headers
    )
    assert response_post.status_code == 401


def test_create_task_invalid_project():
    headers = {"X-API-Key": "dev-key-alice"}
    # project_id 999 does not exist
    response = client.post(
        "/tasks", json={"title": "Test", "project_id": 999}, headers=headers
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Project not found"


def test_create_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    payload = {
        "title": "New automation task",
        "project_id": 1,
        "priority": 1,
        "assigned_to": "bob",
    }
    response = client.post("/tasks", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["title"] == "New automation task"
    assert data["project_id"] == 1
    assert data["priority"] == 1
    assert data["assigned_to"] == "bob"
    assert data["status"] == "todo"  # default status

    # Verify it is in the list
    get_response = client.get(f"/tasks/{data['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["title"] == "New automation task"


def test_update_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.put(
        "/tasks/999", json={"title": "Updated Title"}, headers=headers
    )
    assert response.status_code == 404


def test_update_task_partial():
    headers = {"X-API-Key": "dev-key-alice"}
    # Before update, task 1 has status=done, priority=5, assigned_to=alice
    response = client.put(
        "/tasks/1", json={"status": "in_progress", "priority": 1}, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["priority"] == 1
    assert data["title"] == "Design schema"  # unchanged
    assert data["assigned_to"] == "alice"  # unchanged


def test_delete_task_not_found():
    headers = {"X-API-Key": "dev-key-alice"}
    response = client.delete("/tasks/999", headers=headers)
    assert response.status_code == 404


def test_delete_task_success():
    headers = {"X-API-Key": "dev-key-alice"}
    # Let's delete task 2
    response = client.delete("/tasks/2", headers=headers)
    assert response.status_code == 200

    # Getting it should return 404
    response_get = client.get("/tasks/2")
    assert response_get.status_code == 404
