from fastapi import FastAPI, HTTPException, Depends, Query
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
    page: int = Query(1, gt=0),
    page_size: int = Query(20, gt=0)
):
    filters = {
        'status': status,
        'priority': priority,
        'assigned_to': assigned_to
    }
    filtered_tasks = [task for task in tasks if all(getattr(task, k) == v for k, v in filters.items() if v is not None)]
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]

@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    # Validate project_id
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Auto-generate ID
    task_id = max(t.id for t in tasks) + 1 if tasks else 1
    created_task = Task(id=task_id, **task.dict())
    tasks.append(created_task)
    return created_task

@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
    for index, task in enumerate(tasks):
        if task.id == task_id:
            task_data = task.dict()
            for key, value in task_update.dict(exclude_unset=True).items():
                task_data[key] = value
            tasks[index] = Task(**task_data)
            return tasks[index]
    raise HTTPException(status_code=404, detail="Task not found")

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    for index, task in enumerate(tasks):
        if task.id == task_id:
            del tasks[index]
            return
    raise HTTPException(status_code=404, detail="Task not found")
