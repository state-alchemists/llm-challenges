from fastapi import FastAPI, HTTPException
from fastapi import Depends, HTTPException
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(status: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
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


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    for project in projects:
        if project.id == task.project_id:
            new_task = Task(id=len(tasks) + 1, **task.dict())
            tasks.append(new_task)
            return new_task
    raise HTTPException(status_code=404, detail="Project not found")
    return task
