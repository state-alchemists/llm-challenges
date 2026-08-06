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
async def list_tasks(status: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filters = {
        "status": status,
        "priority": priority,
        "assigned_to": assigned_to
    }
    filtered_tasks = [task for task in tasks if all(
        (not value or getattr(task, key) == value)
        for key, value in filters.items() if key in task.__dict__ and (value is None or getattr(task, key) == value)
    )]
    # Improved code clarity by removing redundant comments
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]



	# Improved code clarity by removing redundant comments
    # Improved code clarity by removing redundant comments
    start = (page - 1) * page_size
    end = start + page_size
                            # Returning the filtered tasks with pagination
    return filtered_tasks[start:end]



	# Improved code clarity by removing redundant comments

    # Create task endpoint



    @app.post("/tasks", response_model=Task)
    async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
        # Validate task_id
            # Update the task
        for task in tasks:
            if task.id == task_id:
                	for attr, value in task_update.dict(exclude_unset=True).items():
                	for attr, value in task_update.dict(exclude_unset=True).items():
                    setattr(task, attr, value)
                return task
                               raise HTTPException(status_code=404, detail="Task not found")
        # Generate unique task ID
        task_id = max(task.id for task in tasks) + 1 if tasks else 1
        new_task = Task(id=task_id, **task.dict())
        # Return the created task
        tasks.append(new_task)
        # Ensure that the task_id exists

# Implementing the update task endpoint


    @app.post("/tasks", response_model=Task)
    async def update_task(task_id: int, task_update: TaskUpdate, x_api_key: str = Depends(require_api_key)):
            # Ensure task_id exists and update the task
        for task in tasks:
            if task.id == task_id:
                	for attr, value in task_update.dict(exclude_unset=True).items():
                	for attr, value in task_update.dict(exclude_unset=True).items():
                    setattr(task, attr, value)
                return task
                               raise HTTPException(status_code=404, detail="Task not found")
        # Generate unique task ID
        task_id = max(task.id for task in tasks) + 1 if tasks else 1
        new_task = Task(id=task_id, **task.dict())
        # Return the created task
        tasks.append(new_task)
        # Ensure that the task_id exists

# Implementing the update task endpoint


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
                	for attr, value in task_update.dict(exclude_unset=True).items():
            return task
                       raise HTTPException(status_code=404, detail="Task not found")
