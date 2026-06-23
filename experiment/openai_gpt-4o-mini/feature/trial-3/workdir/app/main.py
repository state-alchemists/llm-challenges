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
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks 
    filtered_tasks = tasks
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
async def get_task(task_id: int):
    for task in tasks:
    for task in tasks:
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
            filtered_tasks = tasks
@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks 
    filtered_tasks = tasks
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
async def get_task(task_id: int):
    for task in tasks:
    for task in tasks:
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
async def create_task(task_create: TaskCreate):
            if task_create.project_id not in [project.id for project in projects]:
            if task_create.project_id not in [project.id for project in projects]:
                    if task_create.project_id not in [project.id for project in projects]:
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
@app.post("/tasks", response_model=Task)
async def create_task(task_create: TaskCreate):
            if task_create.project_id not in [project.id for project in projects]:
            if task_create.project_id not in [project.id for project in projects]:
                    if task_create.project_id not in [project.id for project in projects]:
                    if task_create.project_id not in [project.id for project in projects]:
                raise HTTPException(status_code=404, detail="Project not found")

                            if task_create.project_id not in [project.id for project in projects]:

@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks 
    filtered_tasks = tasks
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
async def get_task(task_id: int):
    for task in tasks:
    for task in tasks:
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
            filtered_tasks = tasks
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
            filtered_tasks = tasks
                                if task_create.project_id not in [project.id for project in projects]:
                raise HTTPException(status_code=404, detail="Project not found")
    new_task_id = max(task.id for task in tasks) + 1 if tasks else 1
    new_task = Task(
        id=new_task_id,
        title=task_create.title,
        status=task_create.status,
        priority=task_create.priority,
        project_id=task_create.project_id,
        assigned_to=task_create.assigned_to
    )
                                            tasks.append(new_task)
                                                tasks.append(new_task)
                                tasks.append(new_task)
    return new_task

            filtered_tasks = tasks
    if status:
        filtered_tasks = [task for task in filtered_tasks if task.status == status]
    if priority:
        filtered_tasks = [task for task in filtered_tasks if task.priority == priority]
    if assigned_to:
        filtered_tasks = [task for task in filtered_tasks if task.assigned_to == assigned_to]
    start = (page - 1) * page_size
    end = start + page_size
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]


@app.get("/tasks", response_model=List[Task])
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks 
    filtered_tasks = tasks
async def list_tasks(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    assigned_to: Optional[str] = None,
    page: int = 1,
    page_size: int = 20):
    filtered_tasks = tasksstatus: Optional[str] = None, priority: Optional[int] = None, assigned_to: Optional[str] = None, page: int = 1, page_size: int = 20):
    filtered_tasks = tasks
    filtered_tasks = tasks
    filtered_tasks = tasks
async def get_task(task_id: int):
    for task in tasks:
    for task in tasks:
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
