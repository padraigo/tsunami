"""Command-line interface for Sona Mio SD-CSRP.

Subcommands mirror the lifecycle in PRD §2:

    init       State 1 — provision a case, both parents' baselines.
    intake     Epic 1 — Statutory Dual-Intake Income Wizard for one parent.
    addons     Capture §4062 shared add-ons for the closing year.
    attest     Epic 2 — Annual Ledger Attestation (dual sign-off).
    true-up    Epic 3 — Reconciliation event; emits settlement invoice.
    reset      May 1st baseline pivot using the closed year's salaries.
    show       Display the case state, baselines, and ledger.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

from sona_mio import storage
from sona_mio.engine import compute_guideline, compute_true_up
from sona_mio.models import Case, HistoryEntry, Parent
from sona_mio.wizard import confirm, prompt_choice, prompt_decimal, prompt_text

TWELVE = Decimal("12")


# ---------- helpers --------------------------------------------------------
def _money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    v = abs(value)
    return f"{sign}${v:,.2f}"


def _resolve_case_dir(args: argparse.Namespace) -> Path:
    return Path(args.case_dir).expanduser().resolve()


def _print_section(title: str) -> None:
    print()
    print(title)
    print("─" * len(title))


# ---------- subcommands ----------------------------------------------------
def cmd_init(args: argparse.Namespace) -> int:
    case_dir = _resolve_case_dir(args)
    if storage.exists(case_dir) and not args.force:
        print(f"case already exists at {storage.case_path(case_dir)} (use --force to overwrite)", file=sys.stderr)
        return 2

    print("Sona Mio — Case Provisioning (State 1)")
    print("V1 scope: W-2 employees only (PRD FR-1.1). Self-employed income deferred.")
    if not confirm("Confirm both parents are W-2 employees?", default=True):
        print("Aborted: V1 requires W-2 employment.", file=sys.stderr)
        return 2

    children = int(prompt_decimal("Number of children", default=Decimal("1"), minimum=Decimal("1")) or 1)

    def _parent(label: str) -> Parent:
        _print_section(f"Parent {label.upper()}")
        return Parent(
            label=label,
            name=prompt_text("  Display name", default=label.upper()),
            base_salary=prompt_decimal("  Forward-looking base salary (annual)", minimum=Decimal("0")) or Decimal("0"),
            timeshare=prompt_decimal("  Timeshare with children (fraction 0..1)", default=Decimal("0.5"), minimum=Decimal("0")) or Decimal("0.5"),
            filing_status=prompt_choice("  Filing status", ["single", "hoh", "mfj"], default="single"),
        )

    p1 = _parent("p1")
    p2 = _parent("p2")

    cap_raw = prompt_decimal(
        "Stipulated combined-income cap (annual, optional per court order)",
        allow_blank=True,
        minimum=Decimal("0"),
    )

    case = Case(
        children=children,
        p1=p1,
        p2=p2,
        stipulated_income_cap=cap_raw,
        baseline_obligor="p1" if p1.base_salary >= p2.base_salary else "p2",
    )

    # Provisional baseline: 25% × monthly delta of base salaries, one-child default.
    # This is just a seed; the real numbers crystallize after the first `intake`.
    p_high = case.parent(case.baseline_obligor)
    p_low = case.parent("p2" if case.baseline_obligor == "p1" else "p1")
    seed = max(Decimal("0"), (p_high.base_salary - p_low.base_salary) / TWELVE * Decimal("0.20"))
    case.baseline_monthly = seed.quantize(Decimal("0.01"))
    case.expected_interim_paid = (case.baseline_monthly * TWELVE).quantize(Decimal("0.01"))
    case.baseline_effective_date = date.today().isoformat()

    path = storage.save(case, case_dir)
    print()
    print(f"✓ Case {case.case_id} initialized at {path}")
    print(f"  Seed baseline: {case.baseline_obligor.upper()} → {case.parent('p2' if case.baseline_obligor=='p1' else 'p1').label.upper()}  {_money(case.baseline_monthly)}/mo")
    print("  Next: run `sona-mio intake p1` and `sona-mio intake p2` at tax time.")
    return 0


def cmd_intake(args: argparse.Namespace) -> int:
    case = storage.load(_resolve_case_dir(args))
    label = args.parent.lower()
    if label not in ("p1", "p2"):
        print("parent must be 'p1' or 'p2'", file=sys.stderr)
        return 2
    parent = case.parent(label)

    _print_section(f"Statutory Dual-Intake Wizard — {parent.name or label.upper()}")
    print("Input A: base salary (forward-looking baseline)")
    parent.base_salary = prompt_decimal("  Annual base salary", default=parent.base_salary, minimum=Decimal("0")) or parent.base_salary

    print("Input B: consolidated W-2 gross — Form 1040 Line 1a")
    parent.w2_wages = prompt_decimal("  W-2 gross (annual)", minimum=Decimal("0"))

    print("Input C: §4059 mandatory deductions")
    parent.health_premiums = prompt_decimal("  Health insurance premiums", default=parent.health_premiums, minimum=Decimal("0")) or Decimal("0")
    parent.mandatory_retirement = prompt_decimal("  Mandatory retirement contributions", default=parent.mandatory_retirement, minimum=Decimal("0")) or Decimal("0")
    parent.union_dues = prompt_decimal("  Mandatory union dues", default=parent.union_dues, minimum=Decimal("0")) or Decimal("0")

    storage.save(case, _resolve_case_dir(args))
    print(f"\n✓ {label.upper()} intake stored.")
    return 0


def cmd_addons(args: argparse.Namespace) -> int:
    case = storage.load(_resolve_case_dir(args))
    _print_section("§4062 Shared Add-Ons (annual, closing year)")
    case.shared_childcare_cost = prompt_decimal(
        "Employment-related childcare", default=case.shared_childcare_cost, minimum=Decimal("0")
    ) or Decimal("0")
    case.uninsured_medical = prompt_decimal(
        "Uninsured medical costs", default=case.uninsured_medical, minimum=Decimal("0")
    ) or Decimal("0")
    storage.save(case, _resolve_case_dir(args))
    print("✓ Add-ons saved.")
    return 0


def cmd_attest(args: argparse.Namespace) -> int:
    case = storage.load(_resolve_case_dir(args))
    _print_section("Annual Ledger Attestation (Epic 2)")
    print(f"Closing year:            {case.current_year}")
    print(f"Prior baseline:          {case.baseline_obligor.upper()} → owed {_money(case.baseline_monthly)}/mo")
    print(f"Expected total transfer: {_money(case.expected_interim_paid)}")

    print("\nDual sign-off required. Both parents must independently confirm the cleared cash total.")
    a1 = prompt_decimal(f"  {case.p1.name or 'P1'}: actual amount transferred this cycle", minimum=Decimal("0"))
    a2 = prompt_decimal(f"  {case.p2.name or 'P2'}: actual amount transferred this cycle", minimum=Decimal("0"))
    if a1 is None or a2 is None:
        print("Attestation cancelled (no values).", file=sys.stderr)
        return 2
    if a1 != a2:
        print(f"\n× Mismatch: P1 says {_money(a1)}, P2 says {_money(a2)}.")
        print("  Resolve discrepancy out-of-band before re-attesting; ledger unchanged.")
        return 1

    case.attested_interim_paid = a1
    storage.save(case, _resolve_case_dir(args))
    print(f"\n✓ Mutually attested: {_money(a1)}.")
    return 0


def cmd_true_up(args: argparse.Namespace) -> int:
    case_dir = _resolve_case_dir(args)
    case = storage.load(case_dir)
    if case.p1.w2_wages is None or case.p2.w2_wages is None:
        print("Both parents must complete `intake` before true-up.", file=sys.stderr)
        return 2
    if case.attested_interim_paid is None:
        print("Run `attest` before `true-up`.", file=sys.stderr)
        return 2

    guideline = compute_guideline(case)
    invoice = compute_true_up(case, case.current_year, guideline)

    _print_section(f"Reconciliation & True-Up — Year {invoice.closing_year}")
    print(f"Combined monthly NDI:   {_money(guideline.combined_monthly_ndi)}")
    print(f"K factor:               {guideline.k:.4f}")
    print(f"Child multiplier ({case.children}): {guideline.multiplier}")
    print(f"Structural obligor:     {invoice.obligor.upper()} → {invoice.obligee.upper()}")
    print(f"Annual liability:       {_money(invoice.annual_liability)}  ({_money(guideline.monthly_obligation)}/mo)")
    print(f"  base guideline:       {_money(guideline.base_monthly_cs)}/mo")
    print(f"  §4062 add-on share:   {_money(guideline.addon_monthly_share)}/mo")
    print(f"Expected interim paid:  {_money(invoice.expected_interim_paid)}")
    print(f"Attested interim paid:  {_money(invoice.attested_interim_paid)}")
    print()

    if invoice.direction == "owes":
        print(f"INVOICE: {invoice.obligor.upper()} owes {invoice.obligee.upper()} a one-time payment of {_money(invoice.delta)}.")
    elif invoice.direction == "refund":
        print(f"REFUND:  {invoice.obligee.upper()} owes {invoice.obligor.upper()} {_money(-invoice.delta)} (overpayment).")
    else:
        print("SETTLED: no true-up payment due.")

    if args.commit:
        if not confirm("\nCommit this true-up and execute May 1 baseline reset?", default=False):
            print("Not committed.")
            return 0
        # Move forward: archive the closed year, pivot baseline.
        new_baseline_monthly = guideline.monthly_obligation
        history = HistoryEntry(
            year=case.current_year,
            obligor=invoice.obligor,
            annual_liability=invoice.annual_liability,
            expected_interim_paid=invoice.expected_interim_paid,
            attested_interim_paid=invoice.attested_interim_paid,
            true_up_delta=invoice.delta,
            new_baseline_monthly=new_baseline_monthly,
            new_baseline_obligor=invoice.obligor,
            closed_at=date.today().isoformat(),
        )
        case.history.append(history)
        case.current_year += 1
        case.baseline_obligor = invoice.obligor
        case.baseline_monthly = new_baseline_monthly
        case.expected_interim_paid = (new_baseline_monthly * TWELVE).quantize(Decimal("0.01"))
        case.attested_interim_paid = None
        case.shared_childcare_cost = Decimal("0")
        case.uninsured_medical = Decimal("0")
        case.p1.w2_wages = None
        case.p2.w2_wages = None
        # Promote base salary to whatever was last entered during intake.
        case.baseline_effective_date = f"{case.current_year}-05-01"
        storage.save(case, case_dir)
        print(f"✓ Baseline reset: {invoice.obligor.upper()} → {invoice.obligee.upper()}  {_money(new_baseline_monthly)}/mo starting {case.baseline_effective_date}.")
    else:
        print("\n(dry run; pass --commit to archive and pivot the May 1 baseline)")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Force a baseline reset without a full true-up (rare; for corrections)."""
    case_dir = _resolve_case_dir(args)
    case = storage.load(case_dir)
    if case.p1.w2_wages is None or case.p2.w2_wages is None:
        print("Both parents must complete `intake` before reset.", file=sys.stderr)
        return 2
    guideline = compute_guideline(case)
    case.baseline_obligor = guideline.obligor
    case.baseline_monthly = guideline.monthly_obligation
    case.expected_interim_paid = (guideline.monthly_obligation * TWELVE).quantize(Decimal("0.01"))
    case.baseline_effective_date = f"{case.current_year}-05-01"
    storage.save(case, case_dir)
    print(f"✓ Forced baseline reset → {guideline.obligor.upper()} owes {_money(case.baseline_monthly)}/mo from {case.baseline_effective_date}.")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    case = storage.load(_resolve_case_dir(args))
    _print_section("Case")
    print(f"  id:             {case.case_id}")
    print(f"  created:        {case.created_at}")
    print(f"  current year:   {case.current_year}")
    print(f"  children:       {case.children}")
    print(f"  income cap:     {_money(case.stipulated_income_cap)}")
    for p in (case.p1, case.p2):
        _print_section(f"Parent {p.label.upper()} ({p.name or '—'})")
        print(f"  base salary:    {_money(p.base_salary)}")
        print(f"  timeshare:      {p.timeshare}")
        print(f"  filing status:  {p.filing_status}")
        print(f"  W-2 (Line 1a):  {_money(p.w2_wages)}")
        print(f"  §4059 deductions: health {_money(p.health_premiums)}  retire {_money(p.mandatory_retirement)}  union {_money(p.union_dues)}")
    _print_section("Baseline & Ledger")
    print(f"  obligor:               {case.baseline_obligor.upper()}")
    print(f"  monthly:               {_money(case.baseline_monthly)}")
    print(f"  effective:             {case.baseline_effective_date}")
    print(f"  expected interim paid: {_money(case.expected_interim_paid)}")
    print(f"  attested interim paid: {_money(case.attested_interim_paid)}")
    print(f"  §4062 childcare:       {_money(case.shared_childcare_cost)}")
    print(f"  §4062 uninsured med:   {_money(case.uninsured_medical)}")
    if case.history:
        _print_section("History")
        for h in case.history:
            print(f"  {h.year}: {h.obligor.upper()} liability {_money(h.annual_liability)} − attested {_money(h.attested_interim_paid)} = Δ {_money(h.true_up_delta)}  →  new baseline {_money(h.new_baseline_monthly)}/mo")
    return 0


# ---------- argparse plumbing ---------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sona-mio",
        description="Sona Mio SD-CSRP — symmetric dynamic child-support recalculation (CA, W-2 V1).",
    )
    p.add_argument("--case-dir", default=".sona-mio", help="Directory holding the case file (default: ./.sona-mio)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("init", help="Initialize a new case (State 1)")
    s.add_argument("--force", action="store_true", help="Overwrite an existing case file")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("intake", help="Statutory Dual-Intake Income Wizard for one parent (Epic 1)")
    s.add_argument("parent", choices=["p1", "p2"], help="Which parent to capture")
    s.set_defaults(func=cmd_intake)

    s = sub.add_parser("addons", help="Capture §4062 shared add-ons for the closing year")
    s.set_defaults(func=cmd_addons)

    s = sub.add_parser("attest", help="Annual Ledger Attestation — dual sign-off (Epic 2)")
    s.set_defaults(func=cmd_attest)

    s = sub.add_parser("true-up", help="Compute reconciliation invoice (Epic 3)")
    s.add_argument("--commit", action="store_true", help="Archive year, pivot baseline, and reset May 1")
    s.set_defaults(func=cmd_true_up)

    s = sub.add_parser("reset", help="Force a baseline reset from current intake values (corrections)")
    s.set_defaults(func=cmd_reset)

    s = sub.add_parser("show", help="Display current case state")
    s.set_defaults(func=cmd_show)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func: Callable[[argparse.Namespace], int] = args.func
    try:
        return func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
