"""Simplified federal + California + FICA tax estimator.

Used to derive Net Disposable Income from gross W-2 wages for the §4055
guideline calculation. This is intentionally a deterministic approximation,
not a tax-prep substitute — V1 of the platform is bounded to W-2-only
employees (PRD FR-1.1) so the math stays comparable to Line 1a.

Brackets reflect 2024 published values; minor year-over-year shifts can be
configured by passing a custom ``TaxYear`` instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

ZERO = Decimal("0")
TWELVE = Decimal("12")


# -----------------------------------------------------------------------------
# Bracket primitives
# -----------------------------------------------------------------------------
Bracket = tuple[Decimal, Decimal]  # (threshold_upper, marginal_rate)


def _apply_brackets(amount: Decimal, brackets: Iterable[Bracket]) -> Decimal:
    """Apply progressive brackets to ``amount``.

    Each bracket is ``(upper, rate)`` where ``upper`` is the inclusive ceiling
    of the bracket and ``rate`` is the marginal rate on income within it. The
    last bracket's ``upper`` should be a sentinel (e.g. Decimal("Infinity")).
    """
    tax = ZERO
    prior = ZERO
    remaining = amount
    for upper, rate in brackets:
        if remaining <= 0:
            break
        span = upper - prior
        taxable = remaining if remaining < span else span
        tax += taxable * rate
        remaining -= taxable
        prior = upper
    return tax


# -----------------------------------------------------------------------------
# 2024 brackets (single / HoH / MFJ)
# -----------------------------------------------------------------------------
INF = Decimal("1e18")

FEDERAL_2024: dict[str, list[Bracket]] = {
    "single": [
        (Decimal("11600"),  Decimal("0.10")),
        (Decimal("47150"),  Decimal("0.12")),
        (Decimal("100525"), Decimal("0.22")),
        (Decimal("191950"), Decimal("0.24")),
        (Decimal("243725"), Decimal("0.32")),
        (Decimal("609350"), Decimal("0.35")),
        (INF,               Decimal("0.37")),
    ],
    "hoh": [
        (Decimal("16550"),  Decimal("0.10")),
        (Decimal("63100"),  Decimal("0.12")),
        (Decimal("100500"), Decimal("0.22")),
        (Decimal("191950"), Decimal("0.24")),
        (Decimal("243700"), Decimal("0.32")),
        (Decimal("609350"), Decimal("0.35")),
        (INF,               Decimal("0.37")),
    ],
    "mfj": [
        (Decimal("23200"),  Decimal("0.10")),
        (Decimal("94300"),  Decimal("0.12")),
        (Decimal("201050"), Decimal("0.22")),
        (Decimal("383900"), Decimal("0.24")),
        (Decimal("487450"), Decimal("0.32")),
        (Decimal("731200"), Decimal("0.35")),
        (INF,               Decimal("0.37")),
    ],
}

FEDERAL_STANDARD_DEDUCTION_2024: dict[str, Decimal] = {
    "single": Decimal("14600"),
    "hoh":    Decimal("21900"),
    "mfj":    Decimal("29200"),
}

CA_2024: dict[str, list[Bracket]] = {
    "single": [
        (Decimal("10756"),   Decimal("0.01")),
        (Decimal("25499"),   Decimal("0.02")),
        (Decimal("40245"),   Decimal("0.04")),
        (Decimal("55866"),   Decimal("0.06")),
        (Decimal("70606"),   Decimal("0.08")),
        (Decimal("360659"),  Decimal("0.093")),
        (Decimal("432787"),  Decimal("0.103")),
        (Decimal("721314"),  Decimal("0.113")),
        (INF,                Decimal("0.123")),
    ],
    "hoh": [
        (Decimal("21527"),   Decimal("0.01")),
        (Decimal("51000"),   Decimal("0.02")),
        (Decimal("65744"),   Decimal("0.04")),
        (Decimal("81364"),   Decimal("0.06")),
        (Decimal("96107"),   Decimal("0.08")),
        (Decimal("490493"),  Decimal("0.093")),
        (Decimal("588593"),  Decimal("0.103")),
        (Decimal("980987"),  Decimal("0.113")),
        (INF,                Decimal("0.123")),
    ],
    "mfj": [
        (Decimal("21512"),   Decimal("0.01")),
        (Decimal("50998"),   Decimal("0.02")),
        (Decimal("80490"),   Decimal("0.04")),
        (Decimal("111732"),  Decimal("0.06")),
        (Decimal("141212"),  Decimal("0.08")),
        (Decimal("721318"),  Decimal("0.093")),
        (Decimal("865574"),  Decimal("0.103")),
        (Decimal("1442628"), Decimal("0.123")),
        (INF,                Decimal("0.133")),
    ],
}

CA_STANDARD_DEDUCTION_2024: dict[str, Decimal] = {
    "single": Decimal("5540"),
    "hoh":    Decimal("11080"),
    "mfj":    Decimal("11080"),
}

# FICA 2024
SS_RATE = Decimal("0.062")
SS_WAGE_BASE_2024 = Decimal("168600")
MEDICARE_RATE = Decimal("0.0145")
ADDITIONAL_MEDICARE_RATE = Decimal("0.009")
ADDITIONAL_MEDICARE_THRESHOLD = {
    "single": Decimal("200000"),
    "hoh":    Decimal("200000"),
    "mfj":    Decimal("250000"),
}

# NIIT (IRC §1411) — Net Investment Income Tax. Applies to passive rental
# income above MAGI threshold; capped at MAGI excess.
NIIT_RATE = Decimal("0.038")
NIIT_THRESHOLD = {
    "single": Decimal("200000"),
    "hoh":    Decimal("200000"),
    "mfj":    Decimal("250000"),
}


@dataclass
class TaxBreakdown:
    federal: Decimal
    state: Decimal
    fica: Decimal
    niit: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.federal + self.state + self.fica + self.niit


def estimate_total_tax(
    wages: Decimal,
    filing_status: str = "single",
    pretax_deductions: Decimal = ZERO,
    schedule_e_taxable: Decimal = ZERO,
    str_rental: bool = False,
) -> TaxBreakdown:
    """Combined federal + CA + FICA + NIIT estimator for wages and rental.

    ``schedule_e_taxable`` is Schedule E Line 26 (gross rents − cash expenses
    − mortgage interest − depreciation). It may be negative; PAL rules (IRC
    §469) suspend passive losses against W-2 income for high-AGI taxpayers,
    so for income-tax purposes we floor the rental contribution at zero.

    ``str_rental=True`` treats the rental as a trade-or-business (short-term
    rental / Airbnb with substantial services), in which case FICA applies
    to the rental net as well.
    """
    fs = filing_status.lower()
    if fs not in FEDERAL_2024:
        raise ValueError(f"unsupported filing status: {filing_status!r}")

    # PAL: passive losses don't offset W-2 income for high earners (PRD FR-3.4).
    effective_rental = max(ZERO, schedule_e_taxable)
    taxable_combined = wages + effective_rental

    fed_taxable = max(ZERO, taxable_combined - pretax_deductions - FEDERAL_STANDARD_DEDUCTION_2024[fs])
    federal = _apply_brackets(fed_taxable, FEDERAL_2024[fs])

    ca_taxable = max(ZERO, taxable_combined - pretax_deductions - CA_STANDARD_DEDUCTION_2024[fs])
    state = _apply_brackets(ca_taxable, CA_2024[fs])

    # FICA base: wages only by default; STR rental is added per FR-4.4.
    fica_base = wages + (effective_rental if str_rental else ZERO)
    ss = min(fica_base, SS_WAGE_BASE_2024) * SS_RATE
    medicare = fica_base * MEDICARE_RATE
    addl = max(ZERO, fica_base - ADDITIONAL_MEDICARE_THRESHOLD[fs]) * ADDITIONAL_MEDICARE_RATE
    fica = ss + medicare + addl

    # NIIT: 3.8% on net investment income, capped at MAGI excess. STR is
    # earned (Schedule C-equiv) and thus not subject to NIIT.
    if str_rental:
        niit = ZERO
    else:
        nii = effective_rental
        magi_excess = max(ZERO, taxable_combined - NIIT_THRESHOLD[fs])
        niit = min(nii, magi_excess) * NIIT_RATE

    return TaxBreakdown(federal=federal, state=state, fica=fica, niit=niit)


def estimate_annual_tax(
    wages: Decimal,
    filing_status: str = "single",
    pretax_deductions: Decimal = ZERO,
) -> TaxBreakdown:
    """Wages-only tax estimator. Thin wrapper over :func:`estimate_total_tax`
    that keeps the v3.1 W-2-only call sites working unchanged.
    """
    return estimate_total_tax(
        wages=wages,
        filing_status=filing_status,
        pretax_deductions=pretax_deductions,
        schedule_e_taxable=ZERO,
    )
