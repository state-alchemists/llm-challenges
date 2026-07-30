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
async def create_task(task: TaskCreate, x_api_key: str = Depends(require_api_key)) -> Task:
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    task_id = max(t.id for t in tasks) + 1 if tasks else 1
    task_data = task.dict(exclude_unset=True)
    new_task = Task(
        id=task_id,
        title=task_data['title'],
        status=task_data.get('status', TaskStatus.todo),
        priority=task_data.get('priority', 3),
        priority=task_data.get('priority', 1),
        project_id=task.project_id,
        assigned_to=task_data.get('assigned_to')
    )
    tasks.append(new_task)
    return new_task
    if not any(project.id == task.project_id for project in projects):
        raise HTTPException(status_code=404, detail="Project not found")
    task_id = max(t.id for t in tasks) + 1 if tasks else 1
    task_data = task.dict(exclude_unset=True)
    new_task = Task(
        id=task_id,
        title=task_data['title'],
        status=task_data.get('status', TaskStatus.todo),
        priority=task_data.get('priority', 3),
        priority=task_data.get('priority', 1),
        project_id=task.project_id,
        assigned_to=task_data.get('assigned_to')
    )
    tasks.append(new_task)
    return new_task
    filtered_tasks = tasks
    if status:
        filtered_tasks = [t for t in filtered_tasks if t.status == status]
    if priority:
        filtered_tasks = [t for t in filtered_tasks if t.priority == priority]
    if assigned_to:
        filtered_tasks = [t for t in filtered_tasks if t.assigned_to == assigned_to]
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]


@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
