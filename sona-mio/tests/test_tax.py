from decimal import Decimal

from sona_mio.tax import estimate_annual_tax


def test_single_low_income_progressive():
    # $50k single — should land squarely in the 12% federal bracket after std deduction.
    t = estimate_annual_tax(Decimal("50000"), "single")
    # Federal taxable = 50000 - 14600 = 35400, well above 11600 12% threshold.
    assert t.federal > 0
    assert t.fica > 0
    # FICA = 6.2% + 1.45% = 7.65% of full wage (under SS wage base, under addl-medicare).
    expected_fica = Decimal("50000") * Decimal("0.0765")
    assert abs(t.fica - expected_fica) < Decimal("0.01")


def test_high_earner_triggers_additional_medicare():
    t = estimate_annual_tax(Decimal("400000"), "single")
    # Additional 0.9% medicare on wages above $200k single.
    addl_only = Decimal("200000") * Decimal("0.009")
    # FICA should include the additional medicare component.
    base_fica = (
        Decimal("168600") * Decimal("0.062")           # SS capped
        + Decimal("400000") * Decimal("0.0145")        # medicare
    )
    assert abs(t.fica - (base_fica + addl_only)) < Decimal("0.01")


def test_pretax_retirement_reduces_income_tax_only():
    no_retire = estimate_annual_tax(Decimal("150000"), "single", pretax_deductions=Decimal("0"))
    with_retire = estimate_annual_tax(Decimal("150000"), "single", pretax_deductions=Decimal("20000"))
    assert with_retire.federal < no_retire.federal
    assert with_retire.state < no_retire.state
    # FICA is unchanged by retirement-style pretax deductions in this model.
    assert with_retire.fica == no_retire.fica
