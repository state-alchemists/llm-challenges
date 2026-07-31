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
from fastapi import Depends, Query


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = Query(None),
    priority: Optional[int] = Query(None),
    assigned_to: Optional[str] = Query(None),
    page: int = Query(1),
    page_size: int = Query(20),
):
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


@app.post("/tasks", response_model=Task)
async def create_task(task_create: TaskCreate, x_api_key: str = Depends(require_api_key)):
    # Validate project_id
    if not any(project.id == task_create.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")

    # Auto-generate the next task ID
    new_id = max(task.id for task in tasks) + 1 if tasks else 1

    # Create new task
    new_task = Task(id=new_id, **task_create.dict())
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
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


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

    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")






@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    """
    Retrieve a task by its ID.
    """
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")






@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    """
    Retrieve a task by its ID.
    """
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")






@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    """
    Retrieve a task by its ID.
    """
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")






@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    """
    Retrieve a task by its ID.
    """
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")






@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    """
    Retrieve a task by its ID.
    """
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")






@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    """
    Retrieve a task by its ID.
    """
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    """Retrieve a task by its ID."""
    """Retrieve a task by its ID."""
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")







@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


async @app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""



@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""


@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""
@app.delete("/tasks/{task_id}", response_model=Task)
async def delete_task(task_id: int, x_api_key: str = Depends(require_api_key)):
    global tasks
    for i, task in enumerate(tasks):
        if task.id == task_id:
            return tasks.pop(i)
    raise HTTPException(status_code=404, detail="Task not found")
async def get_task(task_id: int):
    """Retrieve a task by its ID."""

async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")

    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


    for task in tasks:
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task
        if task.id == task_id:
            return task

        if task.id == task_id:
            return task

        if task.id == task_id:
            return task


        if task.id == task_id:
                return task
    raise HTTPException(status_code=404, detail="Task not found")


