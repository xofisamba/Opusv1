"""Tests for persistence repository — Tasks 2.2 and 2.3."""
import pytest
import tempfile
import os
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from persistence.models import Base, Project, Scenario, InputSnapshot, ResultSnapshot
from persistence.database import init_db
from persistence.repository import (
    ProjectRepository,
    ScenarioRepository,
    compute_inputs_hash,
    export_project_json,
    import_project_json,
)


@pytest.fixture
def engine():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_engine(f"sqlite:///{path}", echo=False)
    init_db(eng)
    yield eng
    eng.dispose()
    os.unlink(path)


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    sess = Session()
    yield sess
    sess.close()


@pytest.fixture
def project_repo(session):
    return ProjectRepository(session)


@pytest.fixture
def scenario_repo(session):
    return ScenarioRepository(session)


class TestProjectRepository:
    """Task 2.2 — ProjectRepository CRUD + Duplicate."""

    def test_create_project(self, project_repo):
        proj = project_repo.create_project("Solar 1", "solar", "Test")
        assert proj.id is not None
        assert proj.name == "Solar 1"
        assert proj.technology_type == "solar"
        base = [s for s in proj.scenarios if s.is_base_case]
        assert len(base) == 1

    def test_list_projects(self, project_repo):
        p1 = project_repo.create_project("Project A", "solar")
        p2 = project_repo.create_project("Project B", "wind")
        projects = project_repo.list_projects()
        assert len(projects) == 2
        names = {p.name for p in projects}
        assert names == {"Project A", "Project B"}

    def test_get_project(self, project_repo):
        created = project_repo.create_project("My Project", "solar")
        loaded = project_repo.get_project(created.id)
        assert loaded is not None
        assert loaded.name == "My Project"

    def test_delete_project(self, project_repo):
        proj = project_repo.create_project("ToDelete", "solar")
        pid = proj.id
        project_repo.delete_project(pid)
        assert project_repo.get_project(pid) is None

    def test_duplicate_project(self, project_repo):
        src = project_repo.create_project("Source", "solar")
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26}
        project_repo.save_inputs(src.scenarios[0].id, FakeInputs())
        dup = project_repo.duplicate_project(src.id, "Copy of Source")
        assert dup.name == "Copy of Source"
        assert dup.technology_type == "solar"
        assert len(dup.scenarios) == 1
        loaded_inp = project_repo.load_inputs(dup.scenarios[0].id)
        assert loaded_inp is not None

    def test_save_and_load_inputs(self, project_repo):
        proj = project_repo.create_project("Test", "solar")
        sc = proj.scenarios[0]
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26, "ppa_tariff": 57.0}
        project_repo.save_inputs(sc.id, FakeInputs())
        loaded = project_repo.load_inputs(sc.id)
        assert loaded["capacity_mw"] == 75.26

    def test_hash_computation(self):
        d = {"capacity_mw": 75.26, "ppa_tariff": 57.0}
        h = compute_inputs_hash(d)
        assert len(h) == 64
        assert compute_inputs_hash(d) == h
        d2 = {"capacity_mw": 100.0}
        assert compute_inputs_hash(d2) != h

    def test_cache_hit(self, project_repo):
        proj = project_repo.create_project("CacheTest", "solar")
        sc = proj.scenarios[0]
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26}
        inp_dict = FakeInputs().to_dict()
        h = compute_inputs_hash(inp_dict)
        project_repo.save_inputs(sc.id, FakeInputs())
        project_repo.save_results(sc.id, {"irr": 0.08}, h)
        cached = project_repo.get_cached_result(sc.id, h)
        assert cached is not None
        assert cached["irr"] == 0.08

    def test_cache_miss(self, project_repo):
        proj = project_repo.create_project("CacheMiss", "solar")
        sc = proj.scenarios[0]
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26}
        h = compute_inputs_hash(FakeInputs().to_dict())
        project_repo.save_inputs(sc.id, FakeInputs())
        cached = project_repo.get_cached_result(sc.id, h)
        assert cached is None

    def test_clear_cache(self, project_repo):
        proj = project_repo.create_project("ClearCache", "solar")
        sc = proj.scenarios[0]
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26}
        h = compute_inputs_hash(FakeInputs().to_dict())
        project_repo.save_inputs(sc.id, FakeInputs())
        project_repo.save_results(sc.id, {"irr": 0.08}, h)
        project_repo.clear_cache(sc.id)
        cached = project_repo.get_cached_result(sc.id, h)
        assert cached is None


class TestScenarioRepository:
    """Task 2.3 — Scenario branching, lineage, diff."""

    def test_branch_scenario(self, scenario_repo, project_repo):
        proj = project_repo.create_project("BranchTest", "solar")
        base = proj.scenarios[0]
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26, "ppa_tariff": 57.0}
        project_repo.save_inputs(base.id, FakeInputs())
        branched = scenario_repo.branch_scenario(base.id, "High PPA")
        assert branched.is_base_case is False
        assert branched.parent_scenario_id == base.id
        loaded = project_repo.load_inputs(branched.id)
        assert loaded["ppa_tariff"] == 57.0

    def test_list_scenarios_order(self, scenario_repo, project_repo):
        proj = project_repo.create_project("OrderTest", "solar")
        base = proj.scenarios[0]
        scenario_repo.branch_scenario(base.id, "Child A")
        scenario_repo.branch_scenario(base.id, "Child B")
        scenarios = scenario_repo.list_scenarios(proj.id)
        assert scenarios[0].is_base_case is True
        assert len(scenarios) == 3

    def test_delete_scenario_blocked_if_base_with_siblings(self, scenario_repo, project_repo):
        proj = project_repo.create_project("DeleteBlock", "solar")
        base = proj.scenarios[0]
        scenario_repo.branch_scenario(base.id, "Child")
        with pytest.raises(ValueError, match="Cannot delete Base Case"):
            scenario_repo.delete_scenario(base.id)

    def test_delete_non_base_scenario(self, scenario_repo, project_repo):
        proj = project_repo.create_project("DeleteNonBase", "solar")
        base = proj.scenarios[0]
        child = scenario_repo.branch_scenario(base.id, "ToDelete")
        scenario_repo.delete_scenario(child.id)
        scenarios = scenario_repo.list_scenarios(proj.id)
        assert len(scenarios) == 1

    def test_get_lineage(self, scenario_repo, project_repo):
        proj = project_repo.create_project("LineageTest", "solar")
        base = proj.scenarios[0]
        child1 = scenario_repo.branch_scenario(base.id, "Child 1")
        child2 = scenario_repo.branch_scenario(child1.id, "Child 2")
        lineage = scenario_repo.get_scenario_lineage(child2.id)
        assert len(lineage) == 3
        assert lineage[0] == base
        assert lineage[1] == child1
        assert lineage[2] == child2

    def test_get_diff(self, scenario_repo, project_repo):
        proj = project_repo.create_project("DiffTest", "solar")
        base = proj.scenarios[0]
        class InputsA:
            def to_dict(self):
                return {"info": {"name": "A", "capacity_mw": 75}}
        class InputsB:
            def to_dict(self):
                return {"info": {"name": "B", "capacity_mw": 100}}
        project_repo.save_inputs(base.id, InputsA())
        alt = scenario_repo.branch_scenario(base.id, "Alt")
        project_repo.save_inputs(alt.id, InputsB())
        diff = scenario_repo.get_diff(base.id, alt.id)
        assert "info.capacity_mw" in diff


class TestExportImport:
    """Task 2.5 — JSON export/import."""

    def test_export_import_roundtrip(self, project_repo):
        proj = project_repo.create_project("ExportTest", "solar")
        base = proj.scenarios[0]
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75.26, "ppa_tariff": 57.0}
        project_repo.save_inputs(base.id, FakeInputs())
        json_str = export_project_json(proj.id, project_repo)
        parsed = json.loads(json_str)
        assert parsed["opuscore_version"] == "2.0"
        assert parsed["project"]["name"] == "ExportTest"
        assert len(parsed["scenarios"]) == 1
        new_proj = import_project_json(json_str, project_repo)
        assert new_proj.name == "ExportTest"
        assert len(new_proj.scenarios) == 1

    def test_import_wrong_version_raises(self, project_repo):
        bad_json = json.dumps({
            "opuscore_version": "1.0",
            "project": {"name": "Test", "technology_type": "solar"},
            "scenarios": [],
        })
        with pytest.raises(ValueError, match="not compatible"):
            import_project_json(bad_json, project_repo)

    def test_import_preserves_parent_child_links(self, project_repo, scenario_repo):
        proj = project_repo.create_project("LinkTest", "solar")
        base = proj.scenarios[0]
        scenario_repo.branch_scenario(base.id, "Child")
        class FakeInputs:
            def to_dict(self):
                return {"capacity_mw": 75}
        project_repo.save_inputs(base.id, FakeInputs())
        json_str = export_project_json(proj.id, project_repo)
        new_proj = import_project_json(json_str, project_repo)
        assert new_proj.name == "LinkTest"
        assert len(new_proj.scenarios) == 2
        imported_child = [s for s in new_proj.scenarios if not s.is_base_case][0]
        assert imported_child.parent_scenario_id is not None, "Child scenario must have parent link"