@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int, user: str = Depends(require_api_key)):
    from fastapi import HTTPException, Depends
    task = next((task for task in tasks if task.id == task_id), None)
                                                                                                                                                                                                                                                                                             if task is None:
:
                                                raise HTTPException(status_code=404, detail="Task not found")
    tasks.remove(task)
    return {"detail": "Task deleted"}
