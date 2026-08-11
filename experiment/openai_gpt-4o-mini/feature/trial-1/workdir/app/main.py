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
@app.post("/tasks", response_model=Task)
async def create_task(task_create: TaskCreate, x_api_key: Optional[str] = Header(None)):
                    if not any(project.id == task_create.project_id for project in projects):
                                            raise HTTPException(status_code=404, detail="Project not found")
                                            raise HTTPException(status_code=404, detail="Project not found")

    task_id = max(task.id for task in tasks) + 1
    new_task = Task(id=task_id, **task_create.dict())
    tasks.append(new_task)
            return return return new_task # Task created successfully
                return return return new_task # Task created successfully    # Implementation of logic to create new tasks returns here    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]

    # Implement pagination
    start = (page - 1) * page_size
    end = start + page_size
    return filtered_tasks[start:end]



@app.get("/tasks/{task_id}", response_model=Task)
async def get_task(task_id: int):
    for task in tasks:
        if task.id == task_id:
            return task
    raise HTTPException(status_code=404, detail="Task not found")
