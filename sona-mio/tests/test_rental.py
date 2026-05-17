"""Schedule E rental tests — PRD v3.2 Epic 4 coverage.

The §4058 depreciation add-back rule, FICA exclusion, STR escape hatch,
NIIT thresholding, and PAL handling are the load-bearing pieces. Each
gets a focused test below.
"""
from decimal import Decimal

import pytest

from sona_mio.engine import compute_guideline, parent_ndi
from sona_mio.models import Case, Parent, ScheduleE
from sona_mio.tax import NIIT_RATE, estimate_total_tax


# ─── ScheduleE model invariants ─────────────────────────────────────────────
def test_court_income_excludes_depreciation_by_default():
    se = ScheduleE(
        gross_rents=Decimal("200000"),
        cash_operating_expenses=Decimal("40000"),
        mortgage_interest=Decimal("50000"),
        depreciation=Decimal("30000"),
    )
    # §4058 court income: 200k − 40k − 50k = 110k (depreciation NOT subtracted).
    assert se.court_income == Decimal("110000")
    # IRS Schedule E taxable: 200k − 40k − 50k − 30k = 80k.
    assert se.schedule_e_taxable == Decimal("80000")
    assert se.court_income > se.schedule_e_taxable


def test_depreciation_toggle_subtracts_when_stipulated():
    se = ScheduleE(
        gross_rents=Decimal("200000"),
        cash_operating_expenses=Decimal("40000"),
        mortgage_interest=Decimal("50000"),
        depreciation=Decimal("30000"),
        treat_depreciation_as_cash=True,
    )
    # With toggle on, court income matches Schedule E taxable.
    assert se.court_income == Decimal("80000")


def test_court_income_floors_at_zero():
    """Real cash loss on a rental → court income = 0, not negative.

    Per FR-4.3: a rental that's cash-flow negative doesn't reduce the
    parent's W-2 income for §4055 purposes.
    """
    se = ScheduleE(
        gross_rents=Decimal("50000"),
        cash_operating_expenses=Decimal("30000"),
        mortgage_interest=Decimal("40000"),  # interest alone exceeds rents
        depreciation=Decimal("10000"),
    )
    assert se.court_income == Decimal("0")
    # But the IRS sees an actual loss on Schedule E.
    assert se.schedule_e_taxable == Decimal("-30000")


# ─── Tax estimator: rental-specific channels ────────────────────────────────
def test_fica_not_applied_to_rental_by_default():
    # Same total income, all rental vs all wages — FICA must differ.
    wages_only = estimate_total_tax(
        wages=Decimal("300000"),
        filing_status="single",
        schedule_e_taxable=Decimal("0"),
    )
    rental_only = estimate_total_tax(
        wages=Decimal("0"),
        filing_status="single",
        schedule_e_taxable=Decimal("300000"),
    )
    assert wages_only.fica > Decimal("10000")
    assert rental_only.fica == Decimal("0")


def test_str_flag_applies_fica_to_rental():
    """Short-term rental → Schedule C-equivalent → FICA applies (FR-4.4)."""
    long_term = estimate_total_tax(
        wages=Decimal("100000"),
        filing_status="single",
        schedule_e_taxable=Decimal("100000"),
        str_rental=False,
    )
    short_term = estimate_total_tax(
        wages=Decimal("100000"),
        filing_status="single",
        schedule_e_taxable=Decimal("100000"),
        str_rental=True,
    )
    assert short_term.fica > long_term.fica
    # STR is earned income → no NIIT (NIIT is for passive investment).
    assert short_term.niit == Decimal("0")


def test_niit_applies_above_threshold():
    # Single, $50k wages + $50k rental → combined $100k, BELOW $200k NIIT
    # threshold, so no NIIT.
    low = estimate_total_tax(
        wages=Decimal("50000"),
        filing_status="single",
        schedule_e_taxable=Decimal("50000"),
    )
    assert low.niit == Decimal("0")

    # Single, $300k wages + $100k rental → combined $400k.
    # MAGI excess = 400k − 200k = 200k; NII = 100k → NIIT base = min(100k, 200k) = 100k.
    high = estimate_total_tax(
        wages=Decimal("300000"),
        filing_status="single",
        schedule_e_taxable=Decimal("100000"),
    )
    assert high.niit == Decimal("100000") * NIIT_RATE


def test_niit_capped_at_magi_excess():
    # Single, $210k wages + $100k rental → MAGI excess = 110k, NII = 100k.
    # NIIT base = min(100k, 110k) = 100k.
    t = estimate_total_tax(
        wages=Decimal("210000"),
        filing_status="single",
        schedule_e_taxable=Decimal("100000"),
    )
    assert t.niit == Decimal("100000") * NIIT_RATE

    # Wages just above threshold: $205k wages + $100k rental → MAGI excess = 105k,
    # NII = 100k → NIIT base = 100k. NIIT base capped at NII, not excess.
    t2 = estimate_total_tax(
        wages=Decimal("205000"),
        filing_status="single",
        schedule_e_taxable=Decimal("100000"),
    )
    assert t2.niit == Decimal("100000") * NIIT_RATE

    # Wages well below threshold, rental pushes over: $150k wages + $100k rental
    # → MAGI excess = 50k, NII = 100k → NIIT base = min(100k, 50k) = 50k.
    t3 = estimate_total_tax(
        wages=Decimal("150000"),
        filing_status="single",
        schedule_e_taxable=Decimal("100000"),
    )
    assert t3.niit == Decimal("50000") * NIIT_RATE


def test_passive_loss_does_not_offset_wages():
    """PAL (FR-3.4): a Schedule E loss must not reduce W-2 tax burden."""
    no_loss = estimate_total_tax(
        wages=Decimal("400000"),
        filing_status="single",
        schedule_e_taxable=Decimal("0"),
    )
    with_paper_loss = estimate_total_tax(
        wages=Decimal("400000"),
        filing_status="single",
        schedule_e_taxable=Decimal("-50000"),
    )
    # Federal/state tax on wages should be identical — loss is suspended.
    assert with_paper_loss.federal == no_loss.federal
    assert with_paper_loss.state == no_loss.state


# ─── Engine integration ────────────────────────────────────────────────────
def test_parent_ndi_combines_wages_and_rental():
    p = Parent(
        label="p1",
        w2_wages=Decimal("280000"),
        filing_status="single",
        schedule_e=ScheduleE(
            gross_rents=Decimal("200000"),
            cash_operating_expenses=Decimal("40000"),
            mortgage_interest=Decimal("50000"),
            depreciation=Decimal("30000"),
        ),
    )
    n = parent_ndi(p)
    # Court total = wages 280k + court rental 110k = 390k (NOT 280 + 80).
    assert n.wages == Decimal("280000")
    assert n.court_rental_income == Decimal("110000")
    assert n.court_total_income == Decimal("390000")
    # IRS sees Schedule E taxable of 80k.
    assert n.schedule_e_taxable == Decimal("80000")
    # NDI = court_total − taxes − §4059. Must be positive at these incomes.
    assert n.annual_ndi > Decimal("0")
    assert n.annual_ndi < n.court_total_income


def test_depreciation_tax_benefit_flows_through_to_ndi():
    """A parent with depreciation pays less tax and has higher NDI than a
    parent with identical court_income but no depreciation."""
    no_depr = Parent(
        label="p1", w2_wages=Decimal("0"), filing_status="single",
        schedule_e=ScheduleE(
            gross_rents=Decimal("200000"),
            cash_operating_expenses=Decimal("40000"),
            mortgage_interest=Decimal("50000"),
            depreciation=Decimal("0"),
        ),
    )
    with_depr = Parent(
        label="p1", w2_wages=Decimal("0"), filing_status="single",
        schedule_e=ScheduleE(
            gross_rents=Decimal("200000"),
            cash_operating_expenses=Decimal("40000"),
            mortgage_interest=Decimal("50000"),
            depreciation=Decimal("30000"),
        ),
    )
    n1 = parent_ndi(no_depr)
    n2 = parent_ndi(with_depr)
    # Same court income.
    assert n1.court_total_income == n2.court_total_income
    # But depreciation saves tax → higher NDI for the depreciating parent.
    assert n2.taxes.total < n1.taxes.total
    assert n2.annual_ndi > n1.annual_ndi


def test_rental_only_parent_works():
    """A parent with rental income but no W-2 should run through the engine."""
    p = Parent(
        label="p2", w2_wages=None, filing_status="hoh",
        schedule_e=ScheduleE(
            gross_rents=Decimal("150000"),
            cash_operating_expenses=Decimal("30000"),
            mortgage_interest=Decimal("20000"),
            depreciation=Decimal("15000"),
        ),
    )
    n = parent_ndi(p)
    assert n.wages == Decimal("0")
    assert n.court_rental_income == Decimal("100000")
    # No FICA on rental.
    assert n.taxes.fica == Decimal("0")
    assert n.annual_ndi > Decimal("0")


def test_compute_guideline_with_rental_raises_obligation():
    """Adding rental to the high earner increases the §4055 result."""
    p1_base = Parent(label="p1", w2_wages=Decimal("1080000"), timeshare=Decimal("0.5"), filing_status="single")
    p2 = Parent(label="p2", w2_wages=Decimal("300000"), timeshare=Decimal("0.5"), filing_status="hoh")
    p1_with_rental = Parent(
        label="p1", w2_wages=Decimal("1080000"), timeshare=Decimal("0.5"), filing_status="single",
        schedule_e=ScheduleE(
            gross_rents=Decimal("200000"),
            cash_operating_expenses=Decimal("40000"),
            mortgage_interest=Decimal("50000"),
            depreciation=Decimal("30000"),
        ),
    )

    no_rental = compute_guideline(Case(children=1, p1=p1_base, p2=p2))
    with_rental = compute_guideline(Case(children=1, p1=p1_with_rental, p2=p2))

    assert no_rental.obligor == "p1"
    assert with_rental.obligor == "p1"
    assert with_rental.monthly_obligation > no_rental.monthly_obligation


def test_intake_required_validates_either_wages_or_rental():
    """Engine should accept rental-only and reject parents with nothing."""
    empty = Case(p1=Parent(label="p1"), p2=Parent(label="p2", w2_wages=Decimal("100000")))
    with pytest.raises(ValueError, match="W-2 wages nor Schedule E"):
        compute_guideline(empty)


def test_schedule_e_roundtrips_through_json():
    se = ScheduleE(
        gross_rents=Decimal("200000"),
        cash_operating_expenses=Decimal("40000"),
        mortgage_interest=Decimal("50000"),
        depreciation=Decimal("30000"),
        treat_depreciation_as_cash=True,
        short_term_rental=True,
    )
    p = Parent(label="p1", w2_wages=Decimal("100000"), schedule_e=se)
    recovered = Parent.from_json(p.to_json())
    assert recovered.schedule_e is not None
    assert recovered.schedule_e.gross_rents == Decimal("200000")
    assert recovered.schedule_e.treat_depreciation_as_cash is True
    assert recovered.schedule_e.short_term_rental is True
    assert recovered.schedule_e.court_income == Decimal("80000")  # toggle on


def test_parent_with_no_rental_serializes_null():
    p = Parent(label="p1", w2_wages=Decimal("100000"))
    assert p.to_json()["schedule_e"] is None
    recovered = Parent.from_json(p.to_json())
    assert recovered.schedule_e is None
