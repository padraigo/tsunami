from decimal import Decimal

import pytest

from sona_mio.engine import (
    child_multiplier,
    compute_guideline,
    compute_true_up,
    k_factor,
)
from sona_mio.models import Case, Parent


def test_k_factor_brackets():
    # §4055(b)(3) — four piecewise regions.
    assert k_factor(Decimal("400")) == Decimal("0.20") + Decimal("400") / Decimal("16000")
    assert k_factor(Decimal("3000")) == Decimal("0.25")
    assert k_factor(Decimal("8000")) == Decimal("0.10") + Decimal("1000") / Decimal("8000")
    assert k_factor(Decimal("20000")) == Decimal("0.12") + Decimal("800") / Decimal("20000")


def test_child_multiplier_table():
    assert child_multiplier(1) == Decimal("1.0")
    assert child_multiplier(2) == Decimal("1.6")
    assert child_multiplier(10) == Decimal("2.86")
    # 11+ falls back to the 10 row per the simplified table.
    assert child_multiplier(11) == Decimal("2.86")
    with pytest.raises(ValueError):
        child_multiplier(0)


def _case(
    p1_wages: str,
    p2_wages: str,
    p1_timeshare: str = "0.5",
    p2_timeshare: str = "0.5",
    children: int = 1,
    addons: str = "0",
    cap: str | None = None,
) -> Case:
    case = Case(
        children=children,
        p1=Parent(label="p1", w2_wages=Decimal(p1_wages), timeshare=Decimal(p1_timeshare)),
        p2=Parent(label="p2", w2_wages=Decimal(p2_wages), timeshare=Decimal(p2_timeshare)),
        shared_childcare_cost=Decimal(addons),
    )
    if cap:
        case.stipulated_income_cap = Decimal(cap)
    return case


def test_high_earner_is_default_obligor_when_timeshares_equal():
    case = _case("400000", "200000")
    result = compute_guideline(case)
    assert result.high_earner == "p1"
    assert result.obligor == "p1"
    assert result.obligee == "p2"
    assert result.monthly_obligation > 0


def test_obligor_inverts_when_high_earner_has_majority_timeshare():
    # P1 earns more BUT has the kids 80% of the time → P2 becomes obligor.
    case = _case("400000", "200000", p1_timeshare="0.8", p2_timeshare="0.2")
    result = compute_guideline(case)
    assert result.high_earner == "p1"
    assert result.obligor == "p2"
    assert result.monthly_obligation > 0


def test_symmetry_swapping_parents_swaps_obligor():
    a = compute_guideline(_case("400000", "200000"))
    b = compute_guideline(_case("200000", "400000"))
    assert a.monthly_obligation == b.monthly_obligation
    assert a.obligor != b.obligor


def test_addons_increase_obligation_pro_rata():
    no_addon = compute_guideline(_case("400000", "200000", addons="0"))
    with_addon = compute_guideline(_case("400000", "200000", addons="12000"))
    assert with_addon.monthly_obligation > no_addon.monthly_obligation
    assert with_addon.addon_monthly_share > 0


def test_stipulated_income_cap_lowers_obligation():
    uncapped = compute_guideline(_case("2000000", "200000"))
    capped = compute_guideline(_case("2000000", "200000", cap="500000"))
    assert capped.monthly_obligation < uncapped.monthly_obligation


def test_intake_required_before_guideline():
    case = Case(p1=Parent(label="p1"), p2=Parent(label="p2", w2_wages=Decimal("100000")))
    with pytest.raises(ValueError, match="W-2"):
        compute_guideline(case)


def test_true_up_requires_attestation():
    case = _case("400000", "200000")
    guideline = compute_guideline(case)
    with pytest.raises(ValueError, match="attestation"):
        compute_true_up(case, 2024, guideline)


def test_true_up_underpayment_creates_owes_invoice():
    case = _case("400000", "200000")
    case.baseline_obligor = "p1"
    guideline = compute_guideline(case)
    # Underpay by $1,000 vs the engine-computed annual liability.
    case.attested_interim_paid = guideline.annual_obligation - Decimal("1000")
    tu = compute_true_up(case, 2024, guideline)
    assert tu.obligor == "p1"
    assert tu.direction == "owes"
    assert tu.delta == Decimal("1000.00")


def test_true_up_overpayment_creates_refund():
    case = _case("400000", "200000")
    case.baseline_obligor = "p1"
    # Pretend P1 dramatically overpaid the interim.
    case.attested_interim_paid = Decimal("999999")
    guideline = compute_guideline(case)
    tu = compute_true_up(case, 2024, guideline)
    assert tu.direction == "refund"
    assert tu.delta < 0


def test_true_up_signs_flip_when_obligor_flipped():
    # Prior year P2 was obligor and paid $10k. This year structural obligor is P1.
    # Engine should net the prior payments as negative — P1's invoice = liability + 10k.
    case = _case("400000", "200000")
    case.baseline_obligor = "p2"
    case.attested_interim_paid = Decimal("10000")
    guideline = compute_guideline(case)
    assert guideline.obligor == "p1"
    tu = compute_true_up(case, 2024, guideline)
    assert tu.delta == guideline.annual_obligation + Decimal("10000")
