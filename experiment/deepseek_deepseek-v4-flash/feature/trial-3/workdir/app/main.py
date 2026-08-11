from fastapi import Depends, FastAPI, HTTPException
from typing import List, Optional
from .models import Task, TaskCreate, TaskUpdate, Project, TaskStatus
from .database import tasks, projects
from .auth import require_api_key

app = FastAPI(title="Project Management API")


@app.get("/projects", response_model=List[Project])
async def list_projects():
    return projects


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    filtered = [
        task
        for task in tasks
        if (status is None or task.status == status)
        and (priority is None or task.priority == priority)
        and (assigned_to is None or task.assigned_to == assigned_to)
    ]
    start = (page - 1) * page_size
    return filtered[start : start + page_size]


@app.post("/tasks", response_model=Task)
async def create_task(task_data: TaskCreate, username: str = Depends(require_api_key)):
    if not any(project.id == task_data.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    new_id = max((task.id for task in tasks), default=0) + 1
    task = Task(id=new_id, **task_data.model_dump())
    tasks.append(task)
    return task


@app.put("/tasks/{task_id}", response_model=Task)
async def update_task(task_id: int, task_data: TaskUpdate, username: str = Depends(require_api_key)):
    for task in tasks:
        if task.id == task_id:
            for field, value in task_data.model_dump(exclude_unset=True).items():
                setattr(task, field, value)
            return task
    raise HTTPException(status_code=404, detail="Task not found")


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, username: str = Depends(require_api_key)):
    for index, task in enumerate(tasks):
        if task.id == task_id:
            del tasks[index]
            return {"detail": "Task deleted"}
    raise HTTPException(status_code=404, detail="Task not found")


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
