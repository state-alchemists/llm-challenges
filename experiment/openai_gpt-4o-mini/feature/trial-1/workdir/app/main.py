from fastapi import FastAPI, HTTPException, Depends
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")

@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    new_task_id = max(task.id for task in tasks) + 1
    new_task = Task(id=new_task_id, **task.dict())
    tasks.append(new_task)
    return new_task

@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    filtered_tasks = tasks
    if status:
        filtered_tasks = [task for task in filtered_tasks if task.status.value == status]
    if priority:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]
    if assigned_to:
        filtered_tasks = [task for task in filtered_tasks if task.assigned_to == assigned_to]

    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            updated_data = task.copy(update=task_update.dict(exclude_unset=True))
            tasks[tasks.index(task)] = updated_data
            return updated_data
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            tasks.remove(task)
            return {"detail": "Task deleted"}
    raise HTTPException(status_code=404, detail="Task not found")
