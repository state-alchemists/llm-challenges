from fastapi import FastAPI, HTTPException
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
    filtered_tasks = [task for task in tasks if (
        (status is None or task.status == status) and
        (priority is None or task.priority == priority) and
        (assigned_to is None or task.assigned_to == assigned_to)
    )]
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate):
    await require_api_key()
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    new_task_id = len(tasks) + 1
    new_task = Task(id=new_task_id, **task.dict())
    tasks.append(new_task)
    return new_task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate):
    await require_api_key()
    for index, task in enumerate(tasks):
        if task.id == task_id:
            updated_task_data = task.dict()
            if task_update.title:
                updated_task_data["title"] = task_update.title
            if task_update.status:
                updated_task_data["status"] = task_update.status
            if task_update.priority:
                updated_task_data["priority"] = task_update.priority
            if task_update.assigned_to:
                updated_task_data["assigned_to"] = task_update.assigned_to
            tasks[index] = Task(**updated_task_data)
            return tasks[index]
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int):
    await require_api_key()
    for index, task in enumerate(tasks):
        if task.id == task_id:
            del tasks[index]
            return
    raise HTTPException(status_code=404, detail="Task not found")

@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    await require_api_key()
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")