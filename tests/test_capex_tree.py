"""Tests for core/domain/capex.py — CapexTree."""
import pytest
from core.domain.capex import (
    CapexItem,
    CapexNode,
    create_generic_capex_tree,
    capex_to_dict,
    capex_from_dict,
    capex_to_json,
    capex_from_json,
)


def test_tree_total_keur_with_leaf_amounts():
    """Test that tree totalKeur equals sum of all leaf amounts."""
    leaf_a = CapexItem(
        code="C.01.01",
        name="EPC",
        parent_code="C.01",
        amount_keur=1000.0,
    )
    leaf_b = CapexItem(
        code="C.02.01",
        name="Modules",
        parent_code="C.02",
        amount_keur=2000.0,
    )
    node_a = CapexNode(code="C.01", name="EPC Group", parent_code=None, children=(leaf_a,))
    node_b = CapexNode(code="C.02", name="Modules Group", parent_code=None, children=(leaf_b,))
    root = CapexNode(code="C", name="Total", parent_code=None, children=(node_a, node_b))

    assert root.total_keur == 3000.0
    assert node_a.total_keur == 1000.0
    assert node_b.total_keur == 2000.0


def test_generic_capex_tree_has_10_nodes():
    """Test that create_generic_capex_tree() returns a tree with 10 child nodes."""
    root = create_generic_capex_tree()
    assert len(root.children) == 10
    assert root.code == "C"
    # All leaf amounts should be 0.0
    assert root.total_keur == 0.0


def test_json_round_trip_preserves_structure():
    """Test that JSON serialization round-trip preserves tree structure."""
    leaf = CapexItem(
        code="C.01.01",
        name="EPC Contract",
        parent_code="C.01",
        amount_keur=5000.0,
        contingency_rate=0.05,
        spending_profile=(0.3, 0.7),
    )
    node = CapexNode(
        code="C.01",
        name="EPC",
        parent_code=None,
        children=(leaf,),
    )

    json_str = capex_to_json(node)
    restored = capex_from_json(json_str)

    assert restored.code == "C.01"
    assert len(restored.children) == 1
    restored_leaf = restored.children[0]
    assert restored_leaf.amount_keur == 5000.0
    assert restored_leaf.contingency_rate == 0.05
    assert restored_leaf.spending_profile == (0.3, 0.7)


def test_dict_round_trip_preserves_leaf_totals():
    """Test that dict round-trip preserves total_keur sum."""
    leaf1 = CapexItem(code="X.01", name="A", parent_code="X", amount_keur=100.0)
    leaf2 = CapexItem(code="X.02", name="B", parent_code="X", amount_keur=200.0)
    node = CapexNode(code="X", name="Group", parent_code=None, children=(leaf1, leaf2))

    d = capex_to_dict(node)
    restored = capex_from_dict(d)

    assert restored.total_keur == 300.0


def test_add_leaf_propagates_to_total():
    """Test that adding a leaf to a node correctly updates total."""
    leaf1 = CapexItem(code="T.01", name="One", parent_code="T", amount_keur=100.0)
    node = CapexNode(code="T", name="Test", parent_code=None, children=(leaf1,))
    assert node.total_keur == 100.0

    # Create a new node with an additional leaf (immutable)
    leaf2 = CapexItem(code="T.02", name="Two", parent_code="T", amount_keur=50.0)
    new_node = CapexNode(code="T", name="Test", parent_code=None, children=(leaf1, leaf2))
    assert new_node.total_keur == 150.0
    # Old node unchanged
    assert node.total_keur == 100.0


def test_contingency_rate_applies():
    """Test that contingency rate correctly inflates amount."""
    leaf = CapexItem(
        code="C.01",
        name="Test",
        parent_code=None,
        amount_keur=1000.0,
        contingency_rate=0.06,
    )
    assert leaf.total_with_contingency == 1060.0


def test_amount_in_period():
    """Test spending profile period allocation."""
    leaf = CapexItem(
        code="C.01",
        name="Test",
        parent_code=None,
        amount_keur=1000.0,
        spending_profile=(0.3, 0.5, 0.2),
    )
    assert leaf.amount_in_period(0) == 300.0  # y0
    assert leaf.amount_in_period(1) == 500.0  # y1
    assert leaf.amount_in_period(2) == 200.0  # y2
    assert leaf.amount_in_period(3) == 0.0   # beyond profile


def test_negative_amount_raises():
    """Test that negative amount raises ValueError."""
    with pytest.raises(ValueError):
        CapexItem(
            code="C.01",
            name="Bad",
            parent_code=None,
            amount_keur=-100.0,
        )
