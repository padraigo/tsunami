# Sona Mio — SD-CSRP

**Symmetric Dynamic Child Support Recalculation Platform** (PRD v3.2, V2 scope).

A California-statute-aware CLI that automates the annual lifecycle of a
co-parenting child-support obligation: forward-looking baseline → interim
monthly payments → Q1 tax-lag attestation → April reconciliation → May 1
baseline pivot. Both parents are modelled symmetrically; the obligor for
each year is derived from the §4055 formula output, not hard-coded.

> **Scope (V2, PRD v3.2):** W-2 wages **and Schedule E (rental real estate)**.
> Schedule C / K-1 / Schedule D income deferred to V3. See
> [docs/prd.md](docs/prd.md) for the full spec.

## Install

```bash
cd sona-mio
pip install -e ".[dev]"
```

## Lifecycle

The CLI follows the state machine in PRD §2:

| State | Command | Purpose |
|-------|---------|---------|
| 1. Provisioning | `sona-mio init` | Create case, capture both parents' baselines, optional stipulated income cap |
| 2. Interim operation | (out-of-band payments) | Parents transfer the agreed monthly baseline |
| 3a. Tax-time intake | `sona-mio intake p1` / `intake p2` | Capture W-2 (Line 1a), §4059 deductions per parent |
| 3b. §4062 add-ons | `sona-mio addons` | Capture shared childcare + uninsured medical for closing year |
| 3c. Attestation | `sona-mio attest` | Dual sign-off on cleared cash transfer (FR-2.2) |
| 3d. Reconciliation | `sona-mio true-up [--commit]` | Compute settlement invoice; with `--commit`, archive year and pivot baseline |
| Inspect anytime | `sona-mio show` | Render full case state, history, ledger |

By default cases live in `./.sona-mio/case.json`. Override with `--case-dir`.

## Example: PRD §5 walkthrough (Q1 Tax Lag + missed payment)

```bash
sona-mio --case-dir ./demo init
# ... (W-2 confirmation, P1 base $400k, P2 base $200k, no cap)

# April Year 1 — both parents file taxes and run intake.
sona-mio --case-dir ./demo intake p1     # Line 1a = $400,000
sona-mio --case-dir ./demo intake p2     # Line 1a = $200,000
sona-mio --case-dir ./demo addons        # shared_childcare_cost = $12,000

# Dual sign-off; P1 missed one month, both attest to $22,000.
sona-mio --case-dir ./demo attest

# Compute the invoice (dry run), then commit the May 1 pivot.
sona-mio --case-dir ./demo true-up
sona-mio --case-dir ./demo true-up --commit
```

## Calculation engine

`sona_mio.engine.compute_guideline` implements:

- **CA Fam. Code §4058 + §4059** — Net Disposable Income. Inputs:
  W-2 wages (Line 1a) and/or **Schedule E rental income** (court income =
  gross rents − cash op-ex − mortgage interest; depreciation is added back
  per *Marriage of Loh* / *Berger*). Deductions: federal income tax, CA
  state, FICA, **NIIT** for high-income passive rental, plus §4059
  mandatory health/retirement/union.
- **CA Fam. Code §4055(b)(3)** — piecewise K factor by combined monthly NDI.
- **CA Fam. Code §4055(b)(4)** — multi-child multiplier (1 → 1.0; 2 → 1.6; …).
- **CA Fam. Code §4062** — childcare + uninsured medical add-ons allocated
  pro-rata to net incomes (CA Fam. Code §4061).
- **Stipulated cap** — optional per-court-order ceiling on combined income.
- **Directional sign inversion** — if the high earner has majority
  timeshare the obligor flips, per the §4055(a) sign convention.
- **Schedule E specifics** (PRD v3.2 Epic 4):
  - FICA *excluded* from rental income by default; STR (Airbnb / trade-or-business) flag flips it on.
  - **NIIT** (3.8%) on passive rental net above MAGI thresholds.
  - **PAL** (IRC §469): rental losses cannot offset W-2 income for high-AGI parents.
  - **Loss floor**: court_rental_income = max(0, ...) — real cash losses don't reduce W-2 income for §4055.
- **True-Up** (FR-3.2) — `annual_liability − attested_interim_paid`,
  with sign-flip handling when the structural obligor changed between
  cycles. Uses the mutually attested ledger exclusively (FR-2.2).

The federal/CA tax estimator (`sona_mio.tax`) uses 2024 brackets and is
deterministic — not a substitute for tax-prep software. It's intentionally
constrained to W-2 wages.

## Testing

```bash
cd sona-mio
pip install -e ".[dev]"
pytest -v
```

## Data schema

Cases serialize to a single `case.json` per the table in PRD §4. Monetary
values use `Decimal` (stored as JSON strings) to avoid float drift across
write/read cycles.
