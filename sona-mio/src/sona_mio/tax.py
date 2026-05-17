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


@dataclass
class TaxBreakdown:
    federal: Decimal
    state: Decimal
    fica: Decimal

    @property
    def total(self) -> Decimal:
        return self.federal + self.state + self.fica


def estimate_annual_tax(
    wages: Decimal,
    filing_status: str = "single",
    pretax_deductions: Decimal = ZERO,
) -> TaxBreakdown:
    """Estimate combined annual tax burden on W-2 ``wages``.

    ``pretax_deductions`` (e.g. mandatory retirement contributions that reduce
    federal/state taxable wages but not FICA) lowers income-tax exposure only.
    """
    fs = filing_status.lower()
    if fs not in FEDERAL_2024:
        raise ValueError(f"unsupported filing status: {filing_status!r}")

    fed_taxable = max(ZERO, wages - pretax_deductions - FEDERAL_STANDARD_DEDUCTION_2024[fs])
    federal = _apply_brackets(fed_taxable, FEDERAL_2024[fs])

    ca_taxable = max(ZERO, wages - pretax_deductions - CA_STANDARD_DEDUCTION_2024[fs])
    state = _apply_brackets(ca_taxable, CA_2024[fs])

    ss = min(wages, SS_WAGE_BASE_2024) * SS_RATE
    medicare = wages * MEDICARE_RATE
    addl = max(ZERO, wages - ADDITIONAL_MEDICARE_THRESHOLD[fs]) * ADDITIONAL_MEDICARE_RATE
    fica = ss + medicare + addl

    return TaxBreakdown(federal=federal, state=state, fica=fica)
