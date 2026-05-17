"""Symmetrical Calculation Engine (Epic 3).

Implements the California guideline formula (CA Fam. Code §4055) on top of
Net Disposable Income derived from §4059 statutory deductions, then adds
§4062 pro-rata add-ons.

Symmetry: the engine treats both parents as parallel entities, never
hard-codes an obligor, and derives directional sign from the formula output.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sona_mio.models import Case, Parent
from sona_mio.tax import ZERO, TaxBreakdown, estimate_total_tax

TWELVE = Decimal("12")
CENT = Decimal("0.01")


# -- §4055 K-factor table ----------------------------------------------------
def k_factor(combined_monthly_ndi: Decimal) -> Decimal:
    """California §4055(b)(3) K factor (monthly combined NDI)."""
    tn = combined_monthly_ndi
    if tn <= Decimal("800"):
        return Decimal("0.20") + (tn / Decimal("16000"))
    if tn <= Decimal("6666"):
        return Decimal("0.25")
    if tn <= Decimal("10000"):
        return Decimal("0.10") + (Decimal("1000") / tn)
    return Decimal("0.12") + (Decimal("800") / tn)


# -- §4055(b)(4) multi-child multiplier --------------------------------------
CHILD_MULTIPLIER: dict[int, Decimal] = {
    1: Decimal("1.0"),
    2: Decimal("1.6"),
    3: Decimal("2.0"),
    4: Decimal("2.3"),
    5: Decimal("2.5"),
    6: Decimal("2.625"),
    7: Decimal("2.75"),
    8: Decimal("2.813"),
    9: Decimal("2.844"),
    10: Decimal("2.86"),
}


def child_multiplier(children: int) -> Decimal:
    if children < 1:
        raise ValueError("children must be >= 1")
    return CHILD_MULTIPLIER.get(children, CHILD_MULTIPLIER[10])


# -- Per-parent NDI ----------------------------------------------------------
@dataclass
class ParentNDI:
    label: str
    wages: Decimal                    # W-2 (Line 1a)
    court_rental_income: Decimal      # §4058 (depreciation added back)
    schedule_e_taxable: Decimal       # what IRS sees (may be < 0)
    court_total_income: Decimal       # wages + court_rental_income
    taxes: TaxBreakdown
    statutory_deductions: Decimal     # §4059
    annual_ndi: Decimal
    monthly_ndi: Decimal

    @property
    def gross(self) -> Decimal:
        """Back-compat alias — court-cognizable total income."""
        return self.court_total_income


def parent_ndi(parent: Parent) -> ParentNDI:
    """Compute one parent's Net Disposable Income per §4059.

    Income mix per PRD v3.2: W-2 wages (Line 1a) and/or Schedule E rental.
    The §4058 court-cognizable income adds depreciation back; the tax
    estimator sees the post-depreciation Schedule E taxable amount.
    """
    has_wages = parent.w2_wages is not None
    has_rental = parent.schedule_e is not None
    if not (has_wages or has_rental):
        raise ValueError(
            f"{parent.label}: neither W-2 wages nor Schedule E provided (run `intake`)"
        )

    wages = parent.w2_wages if has_wages else ZERO
    if has_rental:
        court_rental = parent.schedule_e.court_income
        sched_e_taxable = parent.schedule_e.schedule_e_taxable
        str_flag = parent.schedule_e.short_term_rental
    else:
        court_rental = ZERO
        sched_e_taxable = ZERO
        str_flag = False

    taxes = estimate_total_tax(
        wages=wages,
        filing_status=parent.filing_status,
        pretax_deductions=parent.mandatory_retirement,
        schedule_e_taxable=sched_e_taxable,
        str_rental=str_flag,
    )
    statutory = parent.health_premiums + parent.mandatory_retirement + parent.union_dues
    court_total = wages + court_rental
    annual_ndi = court_total - taxes.total - statutory
    monthly_ndi = annual_ndi / TWELVE

    return ParentNDI(
        label=parent.label,
        wages=wages,
        court_rental_income=court_rental,
        schedule_e_taxable=sched_e_taxable,
        court_total_income=court_total,
        taxes=taxes,
        statutory_deductions=statutory,
        annual_ndi=annual_ndi,
        monthly_ndi=monthly_ndi,
    )


# -- Top-level calculation ---------------------------------------------------
@dataclass
class GuidelineResult:
    obligor: Literal["p1", "p2"]
    obligee: Literal["p1", "p2"]
    p1_ndi: ParentNDI
    p2_ndi: ParentNDI
    combined_monthly_ndi: Decimal
    high_earner: Literal["p1", "p2"]
    k: Decimal
    multiplier: Decimal
    base_monthly_cs: Decimal              # before §4062 add-ons
    addon_monthly_share: Decimal          # pro-rata share for obligor
    monthly_obligation: Decimal           # final, rounded
    annual_obligation: Decimal


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _scale_ndi(p: "ParentNDI", scale: Decimal) -> "ParentNDI":
    """Proportionally shrink NDI when a §4057 stipulated cap binds."""
    return ParentNDI(
        label=p.label,
        wages=p.wages,
        court_rental_income=p.court_rental_income,
        schedule_e_taxable=p.schedule_e_taxable,
        court_total_income=p.court_total_income,
        taxes=p.taxes,
        statutory_deductions=p.statutory_deductions,
        annual_ndi=p.annual_ndi * scale,
        monthly_ndi=p.monthly_ndi * scale,
    )


def compute_guideline(case: Case) -> GuidelineResult:
    """Run the full §4055 + §4059 + §4062 calculation for ``case``.

    The result is symmetric: ``obligor`` is determined by the sign of the
    formula (CA Fam. Code §4055(a) — the high earner is presumptively the
    obligor unless they also have the majority timeshare, which inverts).
    """
    p1 = parent_ndi(case.p1)
    p2 = parent_ndi(case.p2)

    # Apply stipulated cap on combined income if present.
    combined_annual = p1.annual_ndi + p2.annual_ndi
    if case.stipulated_income_cap is not None and combined_annual > case.stipulated_income_cap:
        scale = case.stipulated_income_cap / combined_annual
        p1 = _scale_ndi(p1, scale)
        p2 = _scale_ndi(p2, scale)

    tn = p1.monthly_ndi + p2.monthly_ndi
    if tn <= 0:
        raise ValueError("combined net disposable income is non-positive")

    if p1.monthly_ndi >= p2.monthly_ndi:
        high_earner = "p1"
        hn = p1.monthly_ndi
        high_timeshare = case.p1.timeshare
    else:
        high_earner = "p2"
        hn = p2.monthly_ndi
        high_timeshare = case.p2.timeshare

    k = k_factor(tn)
    mult = child_multiplier(case.children)

    # CS = K × (HN − H% × TN) × multiplier
    # If the high earner has majority timeshare the result flips negative,
    # which symbolically inverts the obligor direction.
    raw = k * (hn - (high_timeshare * tn)) * mult

    if raw >= 0:
        obligor = high_earner
    else:
        obligor = "p2" if high_earner == "p1" else "p1"
        raw = -raw

    obligee = "p2" if obligor == "p1" else "p1"

    # §4062 add-ons — pro-rata to NET incomes (CA Fam. Code §4061).
    obligor_ndi = p1.monthly_ndi if obligor == "p1" else p2.monthly_ndi
    addon_annual_total = case.shared_childcare_cost + case.uninsured_medical
    addon_monthly_total = addon_annual_total / TWELVE
    addon_share = addon_monthly_total * (obligor_ndi / tn) if tn > 0 else ZERO

    monthly = _quantize(raw + addon_share)
    annual = _quantize(monthly * TWELVE)

    return GuidelineResult(
        obligor=obligor,  # type: ignore[arg-type]
        obligee=obligee,  # type: ignore[arg-type]
        p1_ndi=p1,
        p2_ndi=p2,
        combined_monthly_ndi=tn,
        high_earner=high_earner,  # type: ignore[arg-type]
        k=k,
        multiplier=mult,
        base_monthly_cs=_quantize(raw),
        addon_monthly_share=_quantize(addon_share),
        monthly_obligation=monthly,
        annual_obligation=annual,
    )


# -- True-Up (Epic 3 FR-3.2) -------------------------------------------------
@dataclass
class TrueUp:
    closing_year: int
    obligor: str
    obligee: str
    annual_liability: Decimal      # what the obligor truly owed for the year
    expected_interim_paid: Decimal # 12 × prior baseline
    attested_interim_paid: Decimal # mutually attested actual transfer
    delta: Decimal                 # > 0 → obligor still owes; < 0 → refund due
    direction: Literal["owes", "refund", "settled"]


def compute_true_up(
    case: Case,
    closing_year: int,
    guideline: GuidelineResult,
) -> TrueUp:
    """Compute the settlement invoice using the attested ledger.

    Per FR-2.2 / FR-3.2, the engine relies exclusively on the mutually
    attested ``attested_interim_paid`` value.
    """
    if case.attested_interim_paid is None:
        raise ValueError("attestation incomplete: run `attest` before `true-up`")

    # If the structural obligor flipped vs the prior baseline, the prior
    # interim payments went the "wrong way" relative to the closed year's
    # liability. Net them so the invoice reflects directional truth.
    if case.baseline_obligor == guideline.obligor:
        signed_paid = case.attested_interim_paid
    else:
        signed_paid = -case.attested_interim_paid

    delta = guideline.annual_obligation - signed_paid
    direction: Literal["owes", "refund", "settled"]
    if delta > 0:
        direction = "owes"
    elif delta < 0:
        direction = "refund"
    else:
        direction = "settled"

    return TrueUp(
        closing_year=closing_year,
        obligor=guideline.obligor,
        obligee=guideline.obligee,
        annual_liability=guideline.annual_obligation,
        expected_interim_paid=case.expected_interim_paid,
        attested_interim_paid=case.attested_interim_paid,
        delta=_quantize(delta),
        direction=direction,
    )
