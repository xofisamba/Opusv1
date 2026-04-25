"""Capex Tree — Blueprint §2.1.

Hierarchical CAPEX structure with 10-node tree.
All classes are frozen/immutable.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union
import json


@dataclass(frozen=True)
class CapexItem:
    """Single CAPEX line item.

    Corresponds to Blueprint §2.1 schema.
    """
    code: str  # e.g., "C.02.01.03"
    name: str
    parent_code: Optional[str]  # None for root-level items
    amount_keur: float
    contingency_rate: float = 0.0  # 0.06 = 6%
    spending_profile: tuple[float, ...] = ()  # fraction per period (sum = 1.0)
    capitalize: bool = True
    depreciation_class: str = "asset_main"
    notes: str = ""

    def __post_init__(self):
        if self.amount_keur < 0:
            raise ValueError(f"CapexItem {self.code}: amount cannot be negative")

    @property
    def total_with_contingency(self) -> float:
        return self.amount_keur * (1 + self.contingency_rate)

    def amount_in_period(self, period: int) -> float:
        """Return spend amount for a given period index.

        Per Blueprint §2.1: spending_profile is indexed directly by period.
        period=0 → spending_profile[0], period=1 → spending_profile[1], etc.
        """
        if period < len(self.spending_profile):
            return self.amount_keur * self.spending_profile[period]
        return 0.0


@dataclass(frozen=True)
class CapexNode:
    """Hierarchical CAPEX group node.

    Can contain child CapexNodes (sub-groups) or CapexItems (leafs).
    """
    code: str  # e.g., "C.01", "C.02"
    name: str
    parent_code: Optional[str]
    children: tuple[Union[CapexItem, "CapexNode"], ...] = ()

    @property
    def total_keur(self) -> float:
        """Recursively sum all leaf CapexItems."""
        total = 0.0
        for child in self.children:
            if isinstance(child, CapexItem):
                total += child.amount_keur
            elif isinstance(child, CapexNode):
                total += child.total_keur
        return total

    @property
    def total_with_contingency(self) -> float:
        """Recursively sum all leaf CapexItems with contingency."""
        total = 0.0
        for child in self.children:
            if isinstance(child, CapexItem):
                total += child.total_with_contingency
            elif isinstance(child, CapexNode):
                total += child.total_with_contingency
        return total

    def find_item(self, code: str) -> Optional[CapexItem]:
        """Find a CapexItem by its code."""
        for child in self.children:
            if isinstance(child, CapexItem) and child.code == code:
                return child
            if isinstance(child, CapexNode):
                found = child.find_item(code)
                if found:
                    return found
        return None


@dataclass(frozen=True)
class CapexStructure:
    """Flat CAPEX structure (legacy format from domain/inputs.py).

    Kept for backward compatibility.
    """
    epc_contract: CapexItem
    production_units: CapexItem
    epc_other: CapexItem
    grid_connection: CapexItem
    ops_prep: CapexItem
    insurances: CapexItem
    lease_tax: CapexItem
    construction_mgmt_a: CapexItem
    commissioning: CapexItem
    audit_legal: CapexItem
    construction_mgmt_b: CapexItem
    contingencies: CapexItem
    taxes: CapexItem
    project_acquisition: CapexItem
    project_rights: CapexItem
    idc_keur: float = 0.0
    commitment_fees_keur: float = 0.0
    bank_fees_keur: float = 0.0
    vat_costs_keur: float = 0.0
    reserve_accounts_keur: float = 0.0

    @property
    def total_capex(self) -> float:
        items = [
            self.epc_contract, self.production_units, self.epc_other,
            self.grid_connection, self.ops_prep, self.insurances,
            self.lease_tax, self.construction_mgmt_a, self.commissioning,
            self.audit_legal, self.construction_mgmt_b, self.contingencies,
            self.taxes, self.project_acquisition, self.project_rights,
        ]
        return sum(i.amount_keur for i in items) + self.idc_keur


def create_generic_capex_tree() -> CapexNode:
    """Create a 10-node default CAPEX tree with all leaf amounts = 0.0.

    Per Blueprint §3.3 schema:
    C.01 — EPC Contract
    C.02 — Production Units
    C.03 — Grid Connection
    C.04 — Construction & Installation
    C.05 — Project Rights & Development
    C.06 — Pre-Commissioning & Commissioning
    C.07 — Contingencies
    C.08 — Insurance & Legal
    C.09 — Project Acquisition
    C.10 — VAT & Reserve Accounts
    """
    def make_leaf(code: str, name: str, parent: str) -> CapexItem:
        return CapexItem(
            code=code,
            name=name,
            parent_code=parent,
            amount_keur=0.0,
            contingency_rate=0.0,
            spending_profile=(1.0,),
        )

    def make_node(code: str, name: str, parent: Optional[str], children: tuple) -> CapexNode:
        return CapexNode(
            code=code,
            name=name,
            parent_code=parent,
            children=children,
        )

    # Build leaf nodes
    c0101 = make_leaf("C.01.01", "EPC Contract", "C.01")
    c0102 = make_leaf("C.01.02", "EPC Adjustments", "C.01")

    c0201 = make_leaf("C.02.01", "Solar Modules", "C.02")
    c0202 = make_leaf("C.02.02", "Inverters", "C.02")
    c0203 = make_leaf("C.02.03", "Mounting Systems", "C.02")
    c0204 = make_leaf("C.02.04", " BOS Equipment", "C.02")

    c0301 = make_leaf("C.03.01", "Grid Connection Infrastructure", "C.03")
    c0302 = make_leaf("C.03.02", "Substation", "C.03")

    c0401 = make_leaf("C.04.01", "Civil Works", "C.04")
    c0402 = make_leaf("C.04.02", "Installation Labor", "C.04")

    c0501 = make_leaf("C.05.01", "Land Rights", "C.05")
    c0502 = make_leaf("C.05.02", "Permits & Licenses", "C.05")

    c0601 = make_leaf("C.06.01", "Pre-Commissioning", "C.06")
    c0602 = make_leaf("C.06.02", "Commissioning & Startup", "C.06")

    c0701 = make_leaf("C.07.01", "Contingencies", "C.07")

    c0801 = make_leaf("C.08.01", "Insurance", "C.08")
    c0802 = make_leaf("C.08.02", "Legal & Advisory", "C.08")

    c0901 = make_leaf("C.09.01", "Project Acquisition Fees", "C.09")
    c0902 = make_leaf("C.09.02", "Transaction Advisory", "C.09")

    c1001 = make_leaf("C.10.01", "VAT Costs", "C.10")
    c1002 = make_leaf("C.10.02", "Reserve Accounts", "C.10")
    c1003 = make_leaf("C.10.03", "IDC & Commitment Fees", "C.10")

    # Build group nodes
    c01 = make_node("C.01", "EPC Contract", None, (c0101, c0102))
    c02 = make_node("C.02", "Production Units", None, (c0201, c0202, c0203, c0204))
    c03 = make_node("C.03", "Grid Connection", None, (c0301, c0302))
    c04 = make_node("C.04", "Construction & Installation", None, (c0401, c0402))
    c05 = make_node("C.05", "Project Rights & Development", None, (c0501, c0502))
    c06 = make_node("C.06", "Pre-Commissioning & Commissioning", None, (c0601, c0602))
    c07 = make_node("C.07", "Contingencies", None, (c0701,))
    c08 = make_node("C.08", "Insurance & Legal", None, (c0801, c0802))
    c09 = make_node("C.09", "Project Acquisition", None, (c0901, c0902))
    c10 = make_node("C.10", "VAT & Reserve Accounts", None, (c1001, c1002, c1003))

    # Root node
    root = CapexNode(
        code="C",
        name="Total CAPEX",
        parent_code=None,
        children=(c01, c02, c03, c04, c05, c06, c07, c08, c09, c10),
    )
    return root


def capex_to_dict(node: CapexNode) -> dict:
    """Serialize CapexNode tree to dict for JSON."""
    def serialize_item(item: CapexItem) -> dict:
        return {
            "type": "item",
            "code": item.code,
            "name": item.name,
            "parent_code": item.parent_code,
            "amount_keur": item.amount_keur,
            "contingency_rate": item.contingency_rate,
            "spending_profile": list(item.spending_profile),
            "capitalize": item.capitalize,
            "depreciation_class": item.depreciation_class,
            "notes": item.notes,
        }

    def serialize_node(n: CapexNode) -> dict:
        children_data = []
        for child in n.children:
            if isinstance(child, CapexItem):
                children_data.append(serialize_item(child))
            elif isinstance(child, CapexNode):
                children_data.append(serialize_node(child))
        return {
            "type": "node",
            "code": n.code,
            "name": n.name,
            "parent_code": n.parent_code,
            "children": children_data,
        }

    return serialize_node(node)


def capex_from_dict(data: dict) -> CapexNode:
    """Deserialize dict back to CapexNode tree."""
    def deserialize(d: dict) -> Union[CapexItem, CapexNode]:
        if d.get("type") == "item":
            return CapexItem(
                code=d["code"],
                name=d["name"],
                parent_code=d["parent_code"],
                amount_keur=d["amount_keur"],
                contingency_rate=d.get("contingency_rate", 0.0),
                spending_profile=tuple(d.get("spending_profile", ())),
                capitalize=d.get("capitalize", True),
                depreciation_class=d.get("depreciation_class", "asset_main"),
                notes=d.get("notes", ""),
            )
        else:
            children = tuple(deserialize(c) for c in d.get("children", []))
            return CapexNode(
                code=d["code"],
                name=d["name"],
                parent_code=d["parent_code"],
                children=children,
            )

    return deserialize(data)


def capex_to_json(node: CapexNode) -> str:
    """Serialize CapexNode to JSON string."""
    return json.dumps(capex_to_dict(node), indent=2)


def capex_from_json(s: str) -> CapexNode:
    """Deserialize JSON string to CapexNode."""
    return capex_from_dict(json.loads(s))
