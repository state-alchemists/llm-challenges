from fastapi import FastAPI, HTTPException, Header
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(page: int = 1, page_size: int = 20, status: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None):
    filtered_tasks = tasks
    if status:
        filtered_tasks = [task for task in filtered_tasks if task.status == status]
    if priority:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]
    if assigned_to:
        filtered_tasks = [task for task in filtered_tasks if task.assigned_to == assigned_to]
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    return filtered_tasks[start_index:end_index]

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Header(...)):
    await require_api_key(x_api_key)
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    new_task_id = max(task.id for task in tasks) + 1 if tasks else 1
    new_task = Task(id=new_task_id, **task.dict())
    tasks.append(new_task)
    return new_task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Header(...)):
    await require_api_key(x_api_key)
    task_data = next((task for task in tasks if task.id == task_id), None)
    if task_data:
        task_data.title = task_update.title or task_data.title
        task_data.status = task_update.status or task_data.status
        task_data.priority = task_update.priority or task_data.priority
        task_data.assigned_to = task_update.assigned_to or task_data.assigned_to
        return task_data
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int, x_api_key: str = Header(...)):
    await require_api_key(x_api_key)
    task_data = next((task for task in tasks if task.id == task_id), None)
    if task_data:
        tasks.remove(task_data)
    raise HTTPException(status_code=404, detail="Task not found")