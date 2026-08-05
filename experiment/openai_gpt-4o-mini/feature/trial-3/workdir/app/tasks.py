from typing import Dict, List
from .models import Task, TaskCreate, TaskUpdate, Project, TaskStatus

# Sample tasks data
valid_api_keys: Dict[str, str] = {"dev-key-alice": "alice", "dev-key-bob": "bob"}
tasks: List[Task] = []