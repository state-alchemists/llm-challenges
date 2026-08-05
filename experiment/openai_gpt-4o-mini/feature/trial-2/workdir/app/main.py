from fastapi import FastAPI, HTTPException, Depends
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
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    # Filter tasks based on provided parameters
    filtered_tasks = [task for task in tasks
                      if (status is None or task.status == status) and
                         (priority is None or task.priority == priority) and
                         (assigned_to is None or task.assigned_to == assigned_to)]

    # Implement pagination
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    # Validate project_id
    if task.project_id not in [project.id for project in projects]:
        raise HTTPException(status_code=404, detail='Project not found')
    # Auto-generate ID
    new_id = max(task.id for task in tasks) + 1 if tasks else 1
    new_task = Task(id=new_id, **task.dict())
    tasks.append(new_task)
    return new_task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            if task_update.title is not None:
                task.title = task_update.title
            if task_update.status is not None:
                task.status = task_update.status
            if task_update.priority is not None:
                task.priority = task_update.priority
            if task_update.assigned_to is not None:
                task.assigned_to = task_update.assigned_to
            return task
    raise HTTPException(status_code=404, detail='Task not found')

@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    tasks = [task for task in tasks if task.id != task_id]
    return {'detail': 'Task deleted'}
