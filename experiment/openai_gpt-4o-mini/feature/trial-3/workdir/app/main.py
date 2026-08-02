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
    page: int = Query(1),
    page_size: int = Query(20)
):
    filters = []
    if status:
        filters.append(lambda task: task.status == status)
    if priority:
        filters.append(lambda task: task.priority == priority)
    if assigned_to:
        filters.append(lambda task: task.assigned_to == assigned_to)

    filtered_tasks = tasks
    for filter_func in filters:
        filtered_tasks = list(filter(filter_func, filtered_tasks))

    total_count = len(filtered_tasks)
    start = (page - 1) * page_size
    end = start + page_size
    return list(filtered_tasks)[start:end]

@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, api_key: str = Depends(require_api_key)):
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    task_id = len(tasks) + 1  
    new_task = Task(id=task_id, **task.dict())
    tasks.append(new_task)
    return new_task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_updates: TaskUpdate, api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            if task_updates.title is not None:
                task.title = task_updates.title
            if task_updates.status is not None:
                task.status = task_updates.status
            if task_updates.priority is not None:
                task.priority = task_updates.priority
            if task_updates.assigned_to is not None:
                task.assigned_to = task_updates.assigned_to
            return task
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, api_key: str = Depends(require_api_key)):
    global tasks
    tasks = [task for task in tasks if task.id != task_id]
    return {"detail": "Task deleted"}