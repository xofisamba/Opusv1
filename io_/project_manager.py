"""Project persistence - save/load/delete project configurations.

Uses JSON files in workspace for simple project storage.
Projects are stored as JSON files with all inputs and metadata.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from utils.logging_config import get_logger

from domain.inputs import ProjectInputs

_log = get_logger(__name__)


PROJECTS_DIR = Path("/root/.openclaw/workspace/oborovo_model/projects")
PROJECTS_DIR.mkdir(exist_ok=True)


def _inputs_to_dict(inputs: ProjectInputs) -> dict:
    """Serialize ProjectInputs to dict for JSON storage."""
    # Simple approach: use dataclasses.as_dict but need to handle
    # complex objects. For now, extract key values.
    
    def item_to_dict(obj):
        if hasattr(obj, '__dataclass_fields__'):
            return {k: item_to_dict(v) for k, v in obj.__dict__.items() 
                    if not k.startswith('_')}
        elif isinstance(obj, (list, tuple)):
            return [item_to_dict(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: item_to_dict(v) for k, v in obj.items()}
        elif hasattr(obj, 'value'):  # Enum
            return obj.value
        elif isinstance(obj, (date, datetime)):
            return obj.isoformat()
        else:
            return obj
    
    return item_to_dict(inputs)


def _dict_to_inputs(data: dict) -> ProjectInputs:
    """Reconstruct ProjectInputs from dict."""
    # This is complex because we need to reconstruct all dataclasses
    # For now, just return None and let callers handle
    return None


def save_project(inputs: ProjectInputs, name: str, description: str = "") -> str:
    """Save project inputs to JSON file.
    
    Args:
        inputs: ProjectInputs to save
        name: Project name (will be slugified for filename)
        description: Optional project description
    
    Returns:
        Path to saved project file
    """
    # Slugify name for filename
    slug = name.lower().replace(" ", "_").replace("/", "_").replace("\\", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{slug}_{timestamp}.json"
    filepath = PROJECTS_DIR / filename
    
    project_data = {
        "name": name,
        "description": description,
        "created_at": datetime.now().isoformat(),
        "version": "1.0",
        "inputs": _inputs_to_dict(inputs),
    }
    
    with open(filepath, "w") as f:
        json.dump(project_data, f, indent=2, default=str)
    
    return str(filepath)


def load_project(filepath: str) -> Optional[dict]:
    """Load project from JSON file.
    
    Args:
        filepath: Path to project JSON file
    
    Returns:
        Project dict with name, description, inputs, or None if not found
    """
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def list_projects() -> list[dict]:
    """List all saved projects.
    
    Returns:
        List of project info dicts with name, filename, created_at, description
    """
    projects = []
    
    for f in sorted(PROJECTS_DIR.glob("*.json")):
        try:
            with open(f, "r") as fp:
                data = json.load(fp)
            projects.append({
                "name": data.get("name", f.stem),
                "filename": f.name,
                "filepath": str(f),
                "created_at": data.get("created_at", ""),
                "description": data.get("description", ""),
            })
        except Exception as exc:
            _log.warning("Failed to list project %s: %s", f.name, exc)
            continue
    
    return projects


def delete_project(filepath: str) -> bool:
    """Delete a project file.
    
    Args:
        filepath: Path to project file
    
    Returns:
        True if deleted, False if not found
    """
    try:
        os.remove(filepath)
        return True
    except FileNotFoundError:
        return False


def export_to_json(inputs: ProjectInputs, path: str) -> str:
    """Export project to JSON file (external export).
    
    Args:
        inputs: ProjectInputs to export
        path: Destination path
    
    Returns:
        Path to exported file
    """
    data = {
        "exported_at": datetime.now().isoformat(),
        "version": "1.0",
        "inputs": _inputs_to_dict(inputs),
    }
    
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    
    return path


def import_from_json(path: str) -> Optional[dict]:
    """Import project from JSON file (external import).
    
    Args:
        path: Path to import from
    
    Returns:
        Project dict or None if failed
    """
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception as exc:
        _log.warning("Failed to import project %s: %s", path, exc)
        return None