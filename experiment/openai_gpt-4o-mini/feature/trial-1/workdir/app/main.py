from fastapi import FastAPI, HTTPException, Header
from typing import List
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(x_api_key: str = Header(...), status: str = None, priority: int = None, assigned_to: str = None, page: int = 1, page_size: int = 20) -> List[Task]:
    filtered_tasks = tasks
    if status:
        filtered_tasks = [task for task in filtered_tasks if task.status == status]
    if priority:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]
    if assigned_to:
        filtered_tasks = [task for task in filtered_tasks if task.assigned_to == assigned_to]
    start = (page - 1) * page_size
    end = start + page_size
    # Require authentication
    await require_api_key(x_api_key)
    # Validate project_id exists
    if task_create.project_id not in [project.id for project in projects]:
        raise HTTPException(status_code=404, detail="Project not found")
    # Auto-generate unique task ID
    new_id = max(task.id for task in tasks) + 1 if tasks else 1
    task = Task(id=new_id, **task_create.dict())
    tasks.append(task)
    return task
    # Require authentication
    # Require authentication
    await require_api_key(x_api_key)
    # Validate project_id exists
    if task_create.project_id not in [project.id for project in projects]:
        raise HTTPException(status_code=404, detail="Project not found")
    # Auto-generate unique task ID
    new_id = max(task.id for task in tasks) + 1 if tasks else 1
    task = Task(id=new_id, **task_create.dict())
    tasks.append(task)
    return task


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
