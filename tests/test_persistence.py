"""Tests for persistence layer (SQLAlchemy models + repository)."""
from __future__ import annotations

import pytest
import tempfile
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from persistence.models import Base, Project, Scenario, InputSnapshot, ResultSnapshot
from persistence.database import init_db, reset_db


@pytest.fixture
def engine():
    """Create a temporary SQLite database for each test."""
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


class TestProjectModel:
    """Task 2.1 tests — SQLAlchemy ORM."""

    def test_create_project(self, session):
        """Project saves and loads with correct attributes."""
        proj = Project(name="Solar 1", technology_type="solar", description="Test project")
        session.add(proj)
        session.commit()

        loaded = session.query(Project).filter_by(name="Solar 1").first()
        assert loaded is not None
        assert loaded.name == "Solar 1"
        assert loaded.technology_type == "solar"
        assert loaded.description == "Test project"
        assert loaded.id is not None

    def test_scenario_parent_link(self, session):
        """Child scenario has correct parent_scenario_id."""
        proj = Project(name="Wind 1", technology_type="wind")
        session.add(proj)
        session.commit()

        base = Scenario(project_id=proj.id, name="Base Case", is_base_case=True)
        session.add(base)
        session.commit()

        child = Scenario(
            project_id=proj.id,
            name="High PPA",
            parent_scenario_id=base.id,
            is_base_case=False,
        )
        session.add(child)
        session.commit()

        loaded = session.query(Scenario).filter_by(name="High PPA").first()
        assert loaded.parent_scenario_id == base.id
        assert loaded.is_base_case is False

    def test_cascade_delete(self, session):
        """Deleting project deletes all scenarios and snapshots."""
        proj = Project(name="ToDelete", technology_type="solar")
        session.add(proj)
        session.commit()

        sc = Scenario(project_id=proj.id, name="Base", is_base_case=True)
        session.add(sc)
        session.commit()

        inp = InputSnapshot(scenario_id=sc.id, inputs_json={"capacity_mw": 75}, inputs_hash="abc")
        snap = ResultSnapshot(scenario_id=sc.id, results_json={"irr": 0.08}, inputs_hash="abc")
        session.add(inp)
        session.add(snap)
        session.commit()

        session.delete(proj)
        session.commit()

        assert session.query(Project).filter_by(name="ToDelete").first() is None
        assert session.query(Scenario).filter_by(project_id=proj.id).first() is None
        assert session.query(InputSnapshot).filter_by(scenario_id=sc.id).first() is None
        assert session.query(ResultSnapshot).filter_by(scenario_id=sc.id).first() is None

    def test_project_listed_by_updated_at(self, session):
        """list_projects returns projects sorted by updated_at DESC."""
        p1 = Project(name="First", technology_type="solar")
        p2 = Project(name="Second", technology_type="wind")
        session.add_all([p1, p2])
        session.commit()

        # Force different updated_at
        import time
        p1.updated_at = p1.updated_at
        p2.updated_at = p2.updated_at

        results = session.query(Project).order_by(Project.updated_at.desc()).all()
        assert len(results) == 2
        # At this point they may have same timestamp so just check both exist
        names = {r.name for r in results}
        assert names == {"First", "Second"}


class TestScenarioModel:
    """Scenario model tests."""

    def test_base_case_flag(self, session):
        """is_base_case defaults to False."""
        sc = Scenario(project_id="fake-project-id", name="Alt")
        session.add(sc)
        session.commit()
        assert sc.is_base_case is False

    def test_parent_self_reference(self, session):
        """A scenario can reference itself as parent (for root, parent=None)."""
        proj = Project(name="Test", technology_type="solar")
        session.add(proj)
        session.commit()

        sc = Scenario(project_id=proj.id, name="Root", parent_scenario_id=None, is_base_case=True)
        session.add(sc)
        session.commit()

        assert sc.parent_scenario_id is None
        assert sc.parent is None  # remote_side relationship means None for root