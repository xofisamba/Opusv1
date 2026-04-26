"""Persistence repository — CRUD + serialization + caching for OpusCore v2.

Implements Tasks 2.2 and 2.3 of Phase 2.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Optional, Any
from dataclasses import is_dataclass, asdict

from persistence.models import (
    Project,
    Scenario,
    InputSnapshot,
    ResultSnapshot,
    ScenarioChangeLog,
)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def compute_inputs_hash(inputs_dict: dict) -> str:
    """Compute SHA256 hex of canonical inputs dict for cache invalidation.

    Tuples are serialised as lists (JSON-compatible).
    datetime/date objects serialised as ISO strings.
    """
    canonical = json.dumps(inputs_dict, sort_keys=True, default=_json_default)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _json_default(obj: Any) -> Any:
    """JSON serializer for non-standard types in inputs dicts."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return list(obj)
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


# ---------------------------------------------------------------------------
# ProjectRepository
# ---------------------------------------------------------------------------

class ProjectRepository:
    """CRUD operations on Project + Scenarios + Snapshots."""

    def __init__(self, session):
        self.session = session

    # ---- Project CRUD ----

    def create_project(
        self, name: str, technology_type: str, description: str = ""
    ) -> Project:
        """Create new project with one empty Base Case scenario."""
        proj = Project(name=name, technology_type=technology_type, description=description)
        self.session.add(proj)
        self.session.flush()  # get proj.id

        base = Scenario(
            project_id=proj.id,
            name="Base Case",
            is_base_case=True,
            parent_scenario_id=None,
        )
        self.session.add(base)
        self.session.commit()
        return proj

    def list_projects(self) -> list[Project]:
        """All projects sorted by updated_at DESC."""
        return (
            self.session.query(Project)
            .order_by(Project.updated_at.desc())
            .all()
        )

    def get_project(self, project_id: str) -> Optional[Project]:
        """Load project with eager loading of scenarios."""
        return (
            self.session.query(Project)
            .filter_by(id=project_id)
            .first()
        )

    def get_project_with_scenarios(self, project_id: str) -> Optional[Project]:
        """Load project with all scenarios (eager via selectinload)."""
        from sqlalchemy.orm import selectinload
        return (
            self.session.query(Project)
            .options(selectinload(Project.scenarios))
            .filter_by(id=project_id)
            .first()
        )

    def delete_project(self, project_id: str) -> None:
        """Delete project and cascade all scenarios/snapshots."""
        proj = self.session.query(Project).filter_by(id=project_id).first()
        if proj:
            self.session.delete(proj)
            self.session.commit()

    def duplicate_project(self, project_id: str, new_name: str) -> Project:
        """Deep-copy a project: all scenarios (inputs only, no results).

        Parent-child links between scenarios are preserved.
        Results are NOT copied (must be recomputed).
        """
        src = self.get_project_with_scenarios(project_id)
        if not src:
            raise ValueError(f"Project {project_id} not found")

        new_proj = Project(
            name=new_name,
            technology_type=src.technology_type,
            description=src.description,
        )
        self.session.add(new_proj)
        self.session.flush()

        # Map old scenario ID -> new scenario ID
        id_map: dict[str, Scenario] = {}

        for sc in src.scenarios:
            new_sc = Scenario(
                project_id=new_proj.id,
                name=sc.name,
                parent_scenario_id=None,  # will patch after map
                is_base_case=sc.is_base_case,
                description=sc.description,
            )
            self.session.add(new_sc)
            self.session.flush()
            id_map[sc.id] = new_sc

        # Second pass: restore parent links
        for sc in src.scenarios:
            if sc.parent_scenario_id and sc.parent_scenario_id in id_map:
                new_sc = id_map[sc.id]
                new_sc.parent_scenario_id = id_map[sc.parent_scenario_id].id

        # Copy input snapshots (no results)
        for sc in src.scenarios:
            if sc.input_snapshot:
                inp = sc.input_snapshot
                new_sc = id_map[sc.id]
                new_inp = InputSnapshot(
                    scenario_id=new_sc.id,
                    inputs_json=inp.inputs_json,
                    schema_version=inp.schema_version,
                    inputs_hash=inp.inputs_hash,
                )
                self.session.add(new_inp)

        self.session.commit()
        return new_proj

    def touch_project(self, project_id: str) -> None:
        """Update updated_at timestamp (call after any scenario change)."""
        proj = self.session.query(Project).filter_by(id=project_id).first()
        if proj:
            proj.updated_at = datetime.utcnow()
            self.session.commit()

    # ---- Inputs ----

    def save_inputs(self, scenario_id: str, inputs: Any) -> InputSnapshot:
        """Serialize ProjectInputs → JSON, compute hash, save InputSnapshot.

        Also logs a ScenarioChangeLog entry.
        """
        # Collect previous hash for diff
        prev = self.session.query(InputSnapshot).filter_by(scenario_id=scenario_id).first()
        prev_hash = prev.inputs_hash if prev else None

        inputs_dict = _serialize_inputs(inputs)
        inputs_hash = compute_inputs_hash(inputs_dict)

        # Upsert InputSnapshot
        existing = self.session.query(InputSnapshot).filter_by(scenario_id=scenario_id).first()
        if existing:
            existing.inputs_json = inputs_dict
            existing.inputs_hash = inputs_hash
            existing.created_at = datetime.utcnow()
            inp = existing
        else:
            inp = InputSnapshot(
                scenario_id=scenario_id,
                inputs_json=inputs_dict,
                inputs_hash=inputs_hash,
            )
            self.session.add(inp)

        # Log change
        if prev_hash != inputs_hash:
            log = ScenarioChangeLog(
                scenario_id=scenario_id,
                previous_inputs_hash=prev_hash,
                new_inputs_hash=inputs_hash,
                diff_json=None,  # get_diff called separately
            )
            self.session.add(log)

        self.session.commit()
        self.touch_project_for_scenario(scenario_id)
        return inp

    def load_inputs(self, scenario_id: str) -> Optional[Any]:
        """Deserialize JSON → ProjectInputs object."""
        inp = self.session.query(InputSnapshot).filter_by(scenario_id=scenario_id).first()
        if not inp:
            return None
        return _deserialize_inputs(inp.inputs_json)

    def touch_project_for_scenario(self, scenario_id: str) -> None:
        """Update project updated_at when scenario changes."""
        sc = self.session.query(Scenario).filter_by(id=scenario_id).first()
        if sc:
            proj = self.session.query(Project).filter_by(id=sc.project_id).first()
            if proj:
                proj.updated_at = datetime.utcnow()
                self.session.commit()

    # ---- Results ----

    def save_results(
        self, scenario_id: str, result: Any, inputs_hash: str
    ) -> ResultSnapshot:
        """Save waterfall result (cache entry). inputs_hash must match InputSnapshot."""
        results_dict = _serialize_result(result)
        existing = self.session.query(ResultSnapshot).filter_by(scenario_id=scenario_id).first()
        if existing:
            existing.results_json = results_dict
            existing.computed_at = datetime.utcnow()
            existing.inputs_hash = inputs_hash
            self.session.commit()
            return existing
        else:
            snap = ResultSnapshot(
                scenario_id=scenario_id,
                results_json=results_dict,
                inputs_hash=inputs_hash,
            )
            self.session.add(snap)
            self.session.commit()
            return snap

    def load_results(self, scenario_id: str) -> Optional[Any]:
        """Load cached result (no hash check — use get_cached_result for that)."""
        snap = self.session.query(ResultSnapshot).filter_by(scenario_id=scenario_id).first()
        if not snap:
            return None
        return _deserialize_result(snap.results_json)

    def get_cached_result(self, scenario_id: str, current_inputs_hash: str) -> Optional[Any]:
        """Return cached result if inputs_hash matches, else None (cache miss)."""
        snap = self.session.query(ResultSnapshot).filter_by(scenario_id=scenario_id).first()
        if snap and snap.inputs_hash == current_inputs_hash:
            return _deserialize_result(snap.results_json)
        return None

    def clear_cache(self, scenario_id: str) -> None:
        """Delete result snapshot for a scenario."""
        snap = self.session.query(ResultSnapshot).filter_by(scenario_id=scenario_id).first()
        if snap:
            self.session.delete(snap)
            self.session.commit()


# ---------------------------------------------------------------------------
# ScenarioRepository
# ---------------------------------------------------------------------------

class ScenarioRepository:
    """Scenario-level operations: branching, lineage, diff."""

    def __init__(self, session):
        self.session = session

    def create_base_case(self, project_id: str) -> Scenario:
        """Create a new Base Case scenario for a project."""
        sc = Scenario(
            project_id=project_id,
            name="Base Case",
            is_base_case=True,
            parent_scenario_id=None,
        )
        self.session.add(sc)
        self.session.commit()
        return sc

    def branch_scenario(
        self, parent_scenario_id: str, new_name: str, description: str = ""
    ) -> Scenario:
        """Create a new scenario copying inputs from parent. Results NOT copied."""
        parent = self.session.query(Scenario).filter_by(id=parent_scenario_id).first()
        if not parent:
            raise ValueError(f"Parent scenario {parent_scenario_id} not found")

        new_sc = Scenario(
            project_id=parent.project_id,
            name=new_name,
            parent_scenario_id=parent.id,
            is_base_case=False,
            description=description,
        )
        self.session.add(new_sc)
        self.session.flush()

        # Copy input snapshot
        if parent.input_snapshot:
            inp = InputSnapshot(
                scenario_id=new_sc.id,
                inputs_json=parent.input_snapshot.inputs_json,
                schema_version=parent.input_snapshot.schema_version,
                inputs_hash=parent.input_snapshot.inputs_hash,
            )
            self.session.add(inp)

        self.session.commit()
        return new_sc

    def list_scenarios(self, project_id: str) -> list[Scenario]:
        """All scenarios for project: Base Case first, rest by created_at."""
        scenarios = (
            self.session.query(Scenario)
            .filter_by(project_id=project_id)
            .order_by(Scenario.is_base_case.desc(), Scenario.created_at)
            .all()
        )
        # Move base case to front
        base = [s for s in scenarios if s.is_base_case]
        others = [s for s in scenarios if not s.is_base_case]
        return base + others

    def get_scenario_lineage(self, scenario_id: str) -> list[Scenario]:
        """Return [root, ..., parent, current] chain for breadcrumb."""
        lineage = []
        current = self.session.query(Scenario).filter_by(id=scenario_id).first()
        while current:
            lineage.insert(0, current)
            if current.parent_scenario_id:
                current = self.session.query(Scenario).filter_by(id=current.parent_scenario_id).first()
            else:
                current = None
        return lineage

    def delete_scenario(self, scenario_id: str) -> None:
        """Delete scenario. Base Case cannot be deleted if other scenarios exist."""
        sc = self.session.query(Scenario).filter_by(id=scenario_id).first()
        if not sc:
            return

        # Base case protection
        if sc.is_base_case:
            siblings = (
                self.session.query(Scenario)
                .filter_by(project_id=sc.project_id)
                .count()
            )
            if siblings > 1:
                raise ValueError(
                    "Cannot delete Base Case: project has other scenarios. "
                    "Delete child scenarios first."
                )

        self.session.delete(sc)
        self.session.commit()

    def rename_scenario(self, scenario_id: str, new_name: str) -> None:
        sc = self.session.query(Scenario).filter_by(id=scenario_id).first()
        if sc:
            sc.name = new_name
            self.session.commit()

    def get_diff(
        self, scenario_a_id: str, scenario_b_id: str
    ) -> dict[str, tuple[Any, Any]]:
        """Compare inputs of two scenarios. Returns {field_path: (a_val, b_val)}."""
        inp_a = self.session.query(InputSnapshot).filter_by(scenario_id=scenario_a_id).first()
        inp_b = self.session.query(InputSnapshot).filter_by(scenario_id=scenario_b_id).first()

        if not inp_a or not inp_b:
            return {}

        dict_a = inp_a.inputs_json
        dict_b = inp_b.inputs_json

        return _deep_diff(dict_a, dict_b, prefix="")


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

def export_project_json(project_id: str, project_repo: ProjectRepository) -> str:
    """Export complete project (meta + all scenarios + inputs, no results)."""
    proj = project_repo.get_project(project_id)
    if not proj:
        raise ValueError(f"Project {project_id} not found")

    # Use ScenarioRepository for reliable scenario loading (avoids stale in-memory state)
    sc_repo = ScenarioRepository(project_repo.session)
    all_scenarios = sc_repo.list_scenarios(project_id)

    scenarios_data = []
    for sc in all_scenarios:
        inp_data = None
        if sc.input_snapshot:
            inp_data = sc.input_snapshot.inputs_json
        scenarios_data.append({
            "scenario": {
                "id": sc.id,
                "name": sc.name,
                "parent_scenario_id": sc.parent_scenario_id,
                "is_base_case": sc.is_base_case,
                "description": sc.description,
            },
            "inputs": inp_data,
        })

    return json.dumps({
        "opuscore_version": "2.0",
        "export_timestamp": datetime.utcnow().isoformat(),
        "project": {
            "id": proj.id,
            "name": proj.name,
            "description": proj.description,
            "technology_type": proj.technology_type,
        },
        "scenarios": scenarios_data,
    }, indent=2, default=_json_default)


def import_project_json(json_str: str, project_repo: ProjectRepository) -> Project:
    """Import project from JSON. Creates all scenarios with parent-child links."""
    data = json.loads(json_str)

    version = data.get("opuscore_version", "1.0")
    if not version.startswith("2."):
        raise ValueError(
            f"Import failed: opuscore_version '{version}' not compatible with v2.0"
        )

    proj_meta = data["project"]
    new_proj = Project(
        name=proj_meta["name"],
        technology_type=proj_meta["technology_type"],
        description=proj_meta.get("description", ""),
    )
    project_repo.session.add(new_proj)
    project_repo.session.flush()

    # Map old scenario ID -> new scenario ID
    id_map: dict[str, str] = {}

    # Pass 1: create scenarios
    for sc_data in data["scenarios"]:
        sc_meta = sc_data["scenario"]
        new_sc = Scenario(
            project_id=new_proj.id,
            name=sc_meta["name"],
            parent_scenario_id=None,  # patch in pass 2
            is_base_case=sc_meta["is_base_case"],
            description=sc_meta.get("description", ""),
        )
        project_repo.session.add(new_sc)
        project_repo.session.flush()
        id_map[sc_meta["id"]] = new_sc.id

    # Pass 2: restore parent links
    for sc_data in data["scenarios"]:
        sc_meta = sc_data["scenario"]
        if sc_meta.get("parent_scenario_id") and sc_meta["parent_scenario_id"] in id_map:
            new_id = id_map[sc_meta["id"]]
            new_parent_id = id_map[sc_meta["parent_scenario_id"]]
            sc = project_repo.session.query(Scenario).filter_by(id=new_id).first()
            sc.parent_scenario_id = new_parent_id

    # Pass 3: save inputs
    for sc_data in data["scenarios"]:
        if sc_data.get("inputs"):
            sc_meta = sc_data["scenario"]
            new_sc_id = id_map[sc_meta["id"]]
            inp = InputSnapshot(
                scenario_id=new_sc_id,
                inputs_json=sc_data["inputs"],
                inputs_hash=compute_inputs_hash(sc_data["inputs"]),
            )
            project_repo.session.add(inp)

    project_repo.session.commit()
    return new_proj


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_inputs(inputs: Any) -> dict:
    """Convert ProjectInputs (or any dataclass) to plain dict for JSON."""
    if is_dataclass(inputs):
        return _dataclass_to_dict(inputs)
    if hasattr(inputs, "to_dict"):
        result = inputs.to_dict()
        if isinstance(result, dict):
            return _dataclass_to_dict(result)
        return result
    if hasattr(inputs, "__dict__"):
        return {k: _dataclass_to_dict(v) for k, v in inputs.__dict__.items() if not k.startswith("_")}
    return inputs


def _dataclass_to_dict(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _dataclass_to_dict(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_dataclass_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _dataclass_to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, tuple):
        return [_dataclass_to_dict(x) for x in obj]
    return obj


def _serialize_result(result: Any) -> dict:
    """Serialize WaterfallResult (or similar) to plain dict."""
    return _dataclass_to_dict(result)


def _deserialize_inputs(inputs_dict: dict) -> Any:
    """Reconstruct ProjectInputs from plain dict.

    Since ProjectInputs is a frozen dataclass with nested dataclasses,
    we return the raw dict — the application layer knows how to use it.
    For full fidelity, callers reconstruct via from_dict() on sub-classes.
    """
    return inputs_dict  # raw dict — caller reconstructs


def _deserialize_result(result_dict: dict) -> Any:
    """Reconstruct WaterfallResult from plain dict."""
    return result_dict  # raw dict


def _deep_diff(dict_a: dict, dict_b: dict, prefix: str = "") -> dict[str, tuple[Any, Any]]:
    """Return fields that differ between two inputs dicts."""
    result = {}
    all_keys = set(dict_a.keys()) | set(dict_b.keys())
    for key in all_keys:
        path = f"{prefix}.{key}" if prefix else key
        val_a = dict_a.get(key)
        val_b = dict_b.get(key)
        if val_a != val_b:
            if isinstance(val_a, dict) and isinstance(val_b, dict):
                result.update(_deep_diff(val_a, val_b, path))
            else:
                result[path] = (val_a, val_b)
    return result