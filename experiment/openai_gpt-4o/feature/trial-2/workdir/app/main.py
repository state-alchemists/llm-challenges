from fastapi import FastAPI, HTTPException
from typing import List
from .models import Task, TaskCreate, TaskUpdate, Project
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(status: Optional[str] = None, priority: Optional[str] = None, assigned_to: Optional[str] = None,
                    page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    
    # Apply filters
    if status:
        filtered_tasks = [task for task in filtered_tasks if task.status == status]
    if priority:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]
    if assigned_to:
        filtered_tasks = [task for task in filtered_tasks if task.assigned_to == assigned_to]

    # Apply pagination
    total = len(filtered_tasks)
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.post("/tasks", response_model=Task)
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)):
    # Validate project_id
    if task.project_id not in [project.id for project in projects]:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Auto-generate unique task ID
    new_id = max([t.id for t in tasks] or [0]) + 1
    new_task = Task(id=new_id, **task.dict())
    tasks.append(new_task)
    return new_task
@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
    # Find the task
    for task in tasks:
        if task.id == task_id:
            # Apply partial updates
            task_data = task.dict()
            update_data = task_update.dict(exclude_unset=True)
            task_data.update(update_data)
            updated_task = Task(**task_data)
            tasks[tasks.index(task)] = updated_task
            return updated_task
    raise HTTPException(status_code=404, detail="Task not found")
@app.delete("/tasks/{task_id}", response_model=None)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            tasks.remove(task)
            return
    raise HTTPException(status_code=404, detail="Task not found")
