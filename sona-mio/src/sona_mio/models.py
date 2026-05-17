"""Data schema for Sona Mio cases.

Mirrors the schema in PRD §4. Money values are stored as Decimal strings in
JSON to preserve precision across serialization round-trips.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

ZERO = Decimal("0")


def _d(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    return Decimal(str(value))


@dataclass
class Parent:
    """Per-parent inputs for the symmetric calculation."""

    label: str  # "p1" or "p2"
    name: str = ""
    base_salary: Decimal = ZERO          # forward-looking annual baseline
    timeshare: Decimal = Decimal("0.5")  # fraction 0..1 with the children
    filing_status: str = "single"        # single | hoh | mfj

    # Annual tax-time intake (set during `intake`)
    w2_wages: Decimal | None = None      # Form 1040 Line 1a
    health_premiums: Decimal = ZERO      # §4059
    mandatory_retirement: Decimal = ZERO # §4059
    union_dues: Decimal = ZERO           # §4059

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        if self.w2_wages is not None:
            d["w2_wages"] = str(self.w2_wages)
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Parent":
        return cls(
            label=data["label"],
            name=data.get("name", ""),
            base_salary=_d(data.get("base_salary")),
            timeshare=_d(data.get("timeshare", "0.5")),
            filing_status=data.get("filing_status", "single"),
            w2_wages=_d(data["w2_wages"]) if data.get("w2_wages") not in (None, "") else None,
            health_premiums=_d(data.get("health_premiums")),
            mandatory_retirement=_d(data.get("mandatory_retirement")),
            union_dues=_d(data.get("union_dues")),
        )


@dataclass
class HistoryEntry:
    """A closed reconciliation year."""

    year: int
    obligor: str                # "p1" or "p2"
    annual_liability: Decimal
    expected_interim_paid: Decimal
    attested_interim_paid: Decimal
    true_up_delta: Decimal
    new_baseline_monthly: Decimal
    new_baseline_obligor: str
    closed_at: str

    def to_json(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, Decimal):
                d[k] = str(v)
        return d

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "HistoryEntry":
        return cls(
            year=int(data["year"]),
            obligor=data["obligor"],
            annual_liability=_d(data["annual_liability"]),
            expected_interim_paid=_d(data["expected_interim_paid"]),
            attested_interim_paid=_d(data["attested_interim_paid"]),
            true_up_delta=_d(data["true_up_delta"]),
            new_baseline_monthly=_d(data["new_baseline_monthly"]),
            new_baseline_obligor=data["new_baseline_obligor"],
            closed_at=data["closed_at"],
        )


@dataclass
class Case:
    """Top-level case record (the co-parenting unit)."""

    case_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: date.today().isoformat())
    children: int = 1

    p1: Parent = field(default_factory=lambda: Parent(label="p1"))
    p2: Parent = field(default_factory=lambda: Parent(label="p2"))

    # Annual §4062 add-ons (set during intake for the closing year)
    shared_childcare_cost: Decimal = ZERO
    uninsured_medical: Decimal = ZERO

    # Optional cap per court order
    stipulated_income_cap: Decimal | None = None

    # Lifecycle / state machine
    current_year: int = field(default_factory=lambda: date.today().year)
    baseline_obligor: str = "p1"
    baseline_monthly: Decimal = ZERO
    baseline_effective_date: str = field(default_factory=lambda: date.today().isoformat())

    # Ledger
    expected_interim_paid: Decimal = ZERO       # 12 * baseline_monthly
    attested_interim_paid: Decimal | None = None

    history: list[HistoryEntry] = field(default_factory=list)

    # ---- (de)serialization ----
    def to_json(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "created_at": self.created_at,
            "children": self.children,
            "p1": self.p1.to_json(),
            "p2": self.p2.to_json(),
            "shared_childcare_cost": str(self.shared_childcare_cost),
            "uninsured_medical": str(self.uninsured_medical),
            "stipulated_income_cap": str(self.stipulated_income_cap) if self.stipulated_income_cap is not None else None,
            "current_year": self.current_year,
            "baseline_obligor": self.baseline_obligor,
            "baseline_monthly": str(self.baseline_monthly),
            "baseline_effective_date": self.baseline_effective_date,
            "expected_interim_paid": str(self.expected_interim_paid),
            "attested_interim_paid": str(self.attested_interim_paid) if self.attested_interim_paid is not None else None,
            "history": [h.to_json() for h in self.history],
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Case":
        return cls(
            case_id=data["case_id"],
            created_at=data["created_at"],
            children=int(data.get("children", 1)),
            p1=Parent.from_json(data["p1"]),
            p2=Parent.from_json(data["p2"]),
            shared_childcare_cost=_d(data.get("shared_childcare_cost")),
            uninsured_medical=_d(data.get("uninsured_medical")),
            stipulated_income_cap=_d(data["stipulated_income_cap"]) if data.get("stipulated_income_cap") not in (None, "") else None,
            current_year=int(data.get("current_year", date.today().year)),
            baseline_obligor=data.get("baseline_obligor", "p1"),
            baseline_monthly=_d(data.get("baseline_monthly")),
            baseline_effective_date=data.get("baseline_effective_date", date.today().isoformat()),
            expected_interim_paid=_d(data.get("expected_interim_paid")),
            attested_interim_paid=_d(data["attested_interim_paid"]) if data.get("attested_interim_paid") not in (None, "") else None,
            history=[HistoryEntry.from_json(h) for h in data.get("history", [])],
        )

    def parent(self, label: str) -> Parent:
        if label == "p1":
            return self.p1
        if label == "p2":
            return self.p2
        raise ValueError(f"unknown parent label: {label!r}")
