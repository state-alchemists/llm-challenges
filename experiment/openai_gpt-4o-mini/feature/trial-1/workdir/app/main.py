from fastapi import FastAPI, HTTPException, Query, Depends
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[int] = Query(None),
    assigned_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1)
):
    filtered_tasks = tasks

    if status:
        filtered_tasks = [task for task in filtered_tasks if task.status == status]
    if priority:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]
    if assigned_to:
        filtered_tasks = [task for task in filtered_tasks if task.assigned_to == assigned_to]

    start = (page - 1) * page_size
    end = start + page_size

    return filtered_tasks[start:end]


@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    # Validate project_id
    project_exists = any(project.id == task.project_id for project in projects)
    if not project_exists:
        raise HTTPException(status_code=404, detail="Project not found")

    # Auto-generate a unique ID
    task_id = max(task.id for task in tasks) + 1 if tasks else 1
    new_task = Task(id=task_id, **task.dict())
    tasks.append(new_task)
    return new_task


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, updated_task: TaskUpdate, x_api_key: str = Depends(require_api_key)):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            # Update only fields that are present
            if updated_task.title is not None:
                task.title = updated_task.title
            if updated_task.status is not None:
                task.status = updated_task.status
            if updated_task.priority is not None:
                task.priority = updated_task.priority
            if updated_task.assigned_to is not None:
                task.assigned_to = updated_task.assigned_to
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    tasks = [task for task in tasks if task.id != task_id]
    return {"detail": "Task deleted successfully"}


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")