from fastapi import FastAPI, HTTPException
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from fastapi import Depends
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(status: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20) -> List[Task]:
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


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, api_key: str = Depends(require_api_key)):
    if task.project_id not in [project.id for project in projects]:
        raise HTTPException(status_code=404, detail="Project not found")
    new_id = max(task.id for task in tasks) + 1 if tasks else 1
    new_task = Task(id=new_id, **task.dict())
    tasks.append(new_task)
    return new_task@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            for key, value in task_update.dict(exclude_unset=True).items():
                setattr(task, key, value)
            return task
    raise HTTPException(status_code=404, detail="Task not found")@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, api_key: str = Depends(require_api_key)):
    global tasks
    tasks = [task for task in tasks if task.id != task_id]
    return {"detail": "Task deleted"}