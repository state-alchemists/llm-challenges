from fastapi import FastAPI, HTTPException
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project, TaskStatus
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")

@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects

@app.get("/tasks", response_model=List[Task])
async def list_tasks(status: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    query_filters = []
    if status:
        query_filters.append(lambda task: task.status == TaskStatus[status])
    if priority:
        query_filters.append(lambda task: task.priority == priority)
    if assigned_to:
        query_filters.append(lambda task: task.assigned_to == assigned_to)

    filtered_tasks = [task for task in tasks if all(f(task) for f in query_filters)]
    tasks_to_return = filtered_tasks[(page - 1) * page_size: page * page_size]
    return tasks_to_return

@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
