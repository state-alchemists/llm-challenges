from fastapi import FastAPI, Depends, Query, HTTPException
from .auth import require_api_key
from .database import get_tasks, create_task_in_db, delete_task_in_db, project_exists
from typing import List, Optional

app = FastAPI()

# Existing code...

@app.get("/tasks", response_model=List[Task])
async def read_tasks(status: Optional[str] = None, priority: Optional[str] = None,
                      assigned_to: Optional[str] = None, page: int = Query(1, ge=1),
                      page_size: int = Query(20, ge=1)):
    tasks = get_tasks(status=status, priority=priority, assigned_to=assigned_to)
    start = (page - 1) * page_size
    end = start + page_size
    return tasks[start:end]  # Return paginated tasks

@app.post("/tasks", response_model=Task, dependencies=[Depends(require_api_key)])
async def create_task(project_id: int, task: TaskCreate):
    if not project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    
    new_task = create_task_in_db(task)  # Function implementation here
    return new_task

@app.put("/tasks/{task_id}", response_model=Task, dependencies=[Depends(require_api_key)])
async def update_task(task_id: int, task_update: TaskUpdate):
    task = update_task_in_db(task_id, task_update)  # Function implementation here
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.delete("/tasks/{task_id}", dependencies=[Depends(require_api_key)])
async def delete_task(task_id: int):
    success = delete_task_in_db(task_id)  # Function implementation here
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"detail": "Task removed successfully"}ffrom fastapi import FastAPI, Depends, Query, HTTPException
# Original file content is truncated, likely because of repeating Write call with append flag
