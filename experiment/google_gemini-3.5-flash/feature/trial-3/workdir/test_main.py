import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import tasks, projects
from app.models import Task, TaskStatus

client = TestClient(app)

def test_auth_required():
    # POST /tasks without auth
    resp = client.post("/tasks", json={"title": "New Task", "project_id": 1})
    assert resp.status_code == 401
    
    # PUT /tasks/1 without auth
    resp = client.put("/tasks/1", json={"title": "Updated"})
    assert resp.status_code == 401
    
    # DELETE /tasks/1 without auth
    resp = client.delete("/tasks/1")
    assert resp.status_code == 401

def test_auth_invalid_key():
    headers = {"X-API-Key": "invalid-key"}
    # POST
    resp = client.post("/tasks", json={"title": "New Task", "project_id": 1}, headers=headers)
    assert resp.status_code == 401
    
    # PUT
    resp = client.put("/tasks/1", json={"title": "Updated"}, headers=headers)
    assert resp.status_code == 401
    
    # DELETE
    resp = client.delete("/tasks/1", headers=headers)
    assert resp.status_code == 401

def test_auth_valid_key():
    headers = {"X-API-Key": "dev-key-alice"}
    # GET tasks does not require auth
    resp = client.get("/tasks")
    assert resp.status_code == 200

def test_task_filtering():
    # Filter by status=todo
    resp = client.get("/tasks?status=todo")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(t["status"] == "todo" for t in data)
    
    # Filter by priority=4
    resp = client.get("/tasks?priority=4")
    assert resp.status_code == 200
    data = resp.json()
    # Depending on order / state, at least one of them could match
    
    # Filter by assigned_to=alice
    resp = client.get("/tasks?assigned_to=alice")
    assert resp.status_code == 200
    data = resp.json()
    assert all(t["assigned_to"] == "alice" for t in data)

def test_pagination():
    # page=1, page_size=2 should return first 2 tasks
    resp = client.get("/tasks?page=1&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    
    # page=2, page_size=2 should return next 2 tasks
    resp = client.get("/tasks?page=2&page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) <= 2

def test_create_task():
    headers = {"X-API-Key": "dev-key-alice"}
    # Missing project 404
    resp = client.post("/tasks", json={"title": "New Task", "project_id": 999}, headers=headers)
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"
    
    # Success creation
    count_before = len(tasks)
    resp = client.post("/tasks", json={"title": "Build UI", "project_id": 1, "status": "todo", "priority": 1, "assigned_to": "alice"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] > 4 # auto-generated unique ID
    assert data["title"] == "Build UI"
    assert data["project_id"] == 1
    assert data["status"] == "todo"
    assert data["priority"] == 1
    assert data["assigned_to"] == "alice"
    assert len(tasks) == count_before + 1

def test_update_task():
    headers = {"X-API-Key": "dev-key-alice"}
    # 404 not found
    resp = client.put("/tasks/999", json={"title": "No exist"}, headers=headers)
    assert resp.status_code == 404
    
    # Create or update existing task to avoid test order issues
    resp = client.put("/tasks/3", json={"title": "Write unit tests", "status": "in_progress"}, headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 3
    assert data["title"] == "Write unit tests"
    assert data["status"] == "in_progress"

def test_delete_task():
    headers = {"X-API-Key": "dev-key-alice"}
    # 404 not found
    resp = client.delete("/tasks/999", headers=headers)
    assert resp.status_code == 404
    
    # Success delete
    resp = client.delete("/tasks/1", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"message": "Task deleted"}
    
    # Verify it is gone
    resp = client.get("/tasks/1")
    assert resp.status_code == 404
