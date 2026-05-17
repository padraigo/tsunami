# PRODUCT REQUIREMENTS DOCUMENT (PRD)

**Project Name:** Sona Mio: Symmetric Dynamic Child Support Recalculation Platform (SD-CSRP)
**Document Version:** 3.2 (Non-Wage Income Expansion — Schedule E / Rental)
**Author:** Product Management

## Change Log

| Version | Scope |
|---|---|
| 3.0 | Symmetric architecture (parents as parallel entities) |
| 3.1 | Q1 tax-lag state machine; §4059 deductions; §4062 add-ons; high-earner cap; Annual Ledger Attestation |
| **3.2** | **Schedule E (rental) income; depreciation add-back; NIIT; passive-loss handling. V1 scope expanded to W-2 + Schedule E.** |

## 1. Executive Summary & Objective

The objective of the Sona Mio SD-CSRP is to automate and track annual child-support obligations under California law for co-parents with volatile, high-variance compensation structures.

Version 3.2 expands V1 income scope from W-2-only to **W-2 + Schedule E (rental real estate)**. This addresses the most common non-wage income source for the platform's target demographic — high-earner co-parents whose comp mix includes investment real estate alongside W-2 wages. Schedule C (self-employment) and K-1 (partnership / S-corp) income remain deferred to V3.

Rental income surfaces three statutory and case-law wrinkles absent from the W-2-only flow:
1. **Depreciation add-back** — CA Family Code §4058 and case law (*Marriage of Loh*, *Marriage of Berger*) hold that paper depreciation does not reduce income for child-support purposes, even though it reduces taxable income.
2. **Differential tax treatment** — federal and CA state tax apply; FICA does not (rental is not earned income); the Net Investment Income Tax (NIIT, 3.8%) applies above MAGI thresholds.
3. **Passive Activity Loss limitations** — IRC §469 limits the ability of passive rental losses to offset W-2 income above ~$150k AGI; the engine treats high-earner Schedule E losses as non-offsetting for tax purposes.

## 2. Product Architecture & System States

[Unchanged from v3.1. The Q1-tax-lag-aware calendar (State 1 Provisioning → State 2 Interim Operation → State 3 Reconciliation) holds regardless of income mix.]

### 2.1 State 1: Initialization & Case Provisioning (Year 0)
* Both parents input initial baseline parameters (timeshare splits, tax filing status).
* **High-Earner Override:** Co-parents can set a `stipulated_income_cap` (e.g., capping combined calculated income at $1,000,000 annually) if mandated by their specific court order.

### 2.2 State 2: Interim Baseline Operation (May 1st – April 30th)
* Payments made in Jan/Feb/Mar/Apr are processed under the *previous* year's baseline until the new baseline goes into effect on May 1st.

### 2.3 State 3: Reconciliation & True-Up Event (Tax Season: April)
* The system waits for both users to self-report their finalized IRS Form 1040 parameters **and Schedule E parameters** (v3.2 addition).
* It executes an **Annual Ledger Attestation**, calculates the historical deficit/surplus, issues an explicit settlement invoice, and shifts the forward-looking baseline for the May 1st reset.

## 3. Feature Specifications & Functional Requirements

### Epic 1: The Statutory Dual-Intake Income Wizard

* **FR-1.1: Scope Constraint (V2 W-2 + Schedule E Restriction)** — *UPDATED.* V1 (W-2 only) is superseded by V2: users now verify that their income consists of W-2 wages and/or Schedule E rental real estate. Schedule C (self-employed), Schedule D (capital gains), and K-1 (partnership/S-corp) income remain deferred to V3.

* **FR-1.2: Multi-Step Isolation Wizard:**
  * **Input A (Base Salary):** Recurring base pay only.
  * **Input B (Consolidated W-2 Gross):** IRS Form 1040, Line 1a.
  * **Input C (Statutory Deductions):** Mandatory subtractions per CA Fam. Code §4059 (`health_insurance_premiums`, `mandatory_union_dues`, `mandatory_retirement_contributions`).
  * **Input D (Statutory Add-Ons):** Shared costs per CA Fam. Code §4062 (`employment_related_childcare`, `uninsured_medical_costs`).
  * **Input E (Schedule E — Rental Real Estate):** *NEW in v3.2.* Per-parent aggregation: `gross_rents`, `cash_operating_expenses`, `mortgage_interest`, `depreciation`, `treat_depreciation_as_cash` toggle, `short_term_rental` flag.

* **FR-1.3 (NEW): Schedule E Sub-Wizard** — If a parent answers "yes" to rental ownership, intake branches into the Schedule E flow. Multi-property portfolios are aggregated at the parent level (multi-property line-item entry deferred to V3).

* **FR-1.4 (NEW): Court-Cognizable Rental Income Derivation** — The platform computes:

  ```
  court_rental_income = gross_rents − cash_operating_expenses − mortgage_interest
                        − (depreciation IF treat_depreciation_as_cash else 0)
  court_rental_income = max(0, court_rental_income)
  ```

  This is the §4058 number used in the §4055 engine. Depreciation is excluded by default per CA case law; the toggle exists for orders that explicitly accept depreciation as a real expense (rare; documented as a reviewable deviation).

### Epic 2: Annual Ledger Attestation (The "Imperfect Payer" Protocol)

[Unchanged from v3.1.]

* **FR-2.1: Cash-Flow Verification** — Dashboard displays expected total baseline payments before True-Up fires.
* **FR-2.2: Dual Sign-Off** — Both users must digitally attest to actual amount transferred. True-Up engine relies exclusively on mutually attested `attested_interim_paid`.

### Epic 3: Symmetrical Calculation Engine

* **FR-3.1: Core Formula Execution** — *UPDATED tax model.* The engine computes Net Disposable Income per CA Fam. Code §4059:

  ```
  taxable_income = w2_wages + max(0, schedule_e_net_after_depreciation)
  total_tax = federal(taxable_income) + ca_state(taxable_income)
            + fica(w2_wages [+ rental if STR])
            + niit(rental_net, MAGI_excess)
  court_total_income = w2_wages + court_rental_income     # depreciation NOT subtracted
  NDI = court_total_income − total_tax − §4059_deductions
  ```

  The asymmetry between `taxable_income` (depreciation deducted) and `court_total_income` (depreciation added back) is **the** v3.2 design choice and is documented inline in the engine code.

  After NDI is established, the §4055 guideline runs unchanged:

  ```
  CS = K × (HN − H% × TN) × child_multiplier + §4062_pro_rata_share
  ```

* **FR-3.2: Directional Sign Inversion & True-Up Delta** — [Unchanged.]

* **FR-3.3 (NEW): Non-Wage Income Integration** — Schedule E income participates fully in §4055 derivation but with three engine-level rules:
  1. **FICA exclusion** — Rental income is not earned income; SS/Medicare/Additional Medicare are not applied to the rental portion (default).
  2. **STR escape hatch** — If `short_term_rental = true` (e.g., Airbnb with substantial services), rental flips to Schedule C-equivalent treatment and FICA *does* apply. Documented as a deviation; intake captures the rationale.
  3. **NIIT inclusion** — Above MAGI thresholds ($200k single/HoH, $250k MFJ), the 3.8% Net Investment Income Tax applies to net rental income (capped at MAGI excess).

* **FR-3.4 (NEW): Passive Activity Loss Handling** — Per IRC §469, passive rental losses cannot offset W-2 income for high-AGI taxpayers. The engine implements:
  ```
  effective_rental_for_tax = max(0, schedule_e_taxable)
  ```
  i.e., a Schedule E loss does not reduce W-2 tax liability. The user is informed via a wizard note that suspended PAL losses carry forward at the federal level but do not affect current-year child-support NDI.

### Epic 4 (NEW): Non-Wage Income Handling — Schedule E

* **FR-4.1: Depreciation Add-Back Rule** — Default behavior per *Marriage of Loh* (1999) and *Marriage of Berger* (2009): depreciation is a non-cash tax shield and does not reduce §4058 income. Toggle exists for stipulated orders that accept depreciation; toggle defaults to off and any non-default value is logged in the case history.

* **FR-4.2: Differential Tax Application** — Tax estimator separates the FICA base (wages, plus STR-classified rental) from the income-tax base (wages + Schedule E taxable). NIIT is applied as a third channel.

* **FR-4.3: Loss Floor** — `court_rental_income` is floored at zero. A real cash loss on a rental property does *not* reduce the parent's W-2 income for child-support purposes (CA case law is skeptical of "hobby losses" for high-AGI parents).

* **FR-4.4: STR Trade-or-Business Flag** — Short-term rentals (avg. stay < 7 days, or owner-provided services rising to a trade-or-business level) flip to Schedule C-equivalent tax treatment (FICA applies). Default: false.

* **FR-4.5: Multi-Property Aggregation** — V2 aggregates all rental properties into a single Schedule E record per parent. Per-property line-item tracking is V3.

## 4. Technical Specifications & Data Schema

### 4.1 Case Table (Top-Level)

| Field Name | Data Type | Operational Purpose |
|---|---|---|
| case_id | UUID | Primary Key for the co-parenting unit. |
| stipulated_income_cap | Currency | (Optional) Cap on combined total income. |
| children | Integer | Number of children for §4055(b)(4) multiplier. |
| current_year | Integer | Closing/reconciliation year. |
| baseline_obligor | Enum {p1, p2} | Forward-looking direction. |
| baseline_monthly | Currency | Active monthly transfer amount. |
| baseline_effective_date | Date | When the current baseline took effect. |
| expected_interim_paid | Currency | System-calculated 12-month expected transfer. |
| attested_interim_paid | Currency | User-verified actual cash transferred. |
| shared_childcare_cost | Currency | §4062 add-on (annual). |
| uninsured_medical | Currency | §4062 add-on (annual). |
| history | JSON Array | Closed years with archived true-ups. |

### 4.2 Parent Sub-Schema (Per Co-Parent)

| Field Name | Data Type | Operational Purpose |
|---|---|---|
| label | Enum {p1, p2} | Symmetric identifier. |
| name | String | Display name. |
| base_salary | Currency | Forward-looking baseline. |
| timeshare | Decimal[0,1] | Fraction of time with children. |
| filing_status | Enum {single, hoh, mfj} | For tax estimation. |
| w2_wages | Currency? | Form 1040 Line 1a (nullable until intake). |
| health_premiums | Currency | §4059 deduction. |
| mandatory_retirement | Currency | §4059 deduction. |
| union_dues | Currency | §4059 deduction. |
| **schedule_e** | **ScheduleE?** | **NEW in v3.2 — rental record (nullable).** |

### 4.3 ScheduleE Sub-Schema (Per Parent, Optional) — NEW in v3.2

| Field Name | Data Type | Operational Purpose |
|---|---|---|
| gross_rents | Currency | Total rents received across all properties (annual). |
| cash_operating_expenses | Currency | Real cash expenses: taxes, insurance, repairs, mgmt fees, HOA, utilities. |
| mortgage_interest | Currency | Interest portion of mortgage payments (NOT principal). |
| depreciation | Currency | Annual depreciation reported on Schedule E. Captured for transparency; subtracted from income only if toggle set. |
| treat_depreciation_as_cash | Boolean | Default false. Toggling to true requires court stipulation. |
| short_term_rental | Boolean | Default false. If true, FICA applies (Schedule C-equivalent). |

**Derived properties (computed, not stored):**

| Property | Formula |
|---|---|
| court_income | `max(0, gross_rents − cash_operating_expenses − mortgage_interest − (depreciation IF treat_depreciation_as_cash ELSE 0))` |
| schedule_e_taxable | `gross_rents − cash_operating_expenses − mortgage_interest − depreciation` (can be negative) |

## 5. End-to-End Walkthroughs

### 5.1 Use Case A: The Attested Baseline Pivot (v3.1 — unchanged)

[Q1 tax-lag with missed payments. See v3.1 PRD §5.]

### 5.2 Use Case B (NEW): Mixed W-2 + Rental Calculation

**Pre-conditions:**
- Parent 1: $280k W-2 base salary + $800k W-2 bonus/RSU = $1,080,000 Form 1040 Line 1a.
- Parent 1 also owns a small rental portfolio: $200,000 gross rents; $40,000 cash op-ex; $50,000 mortgage interest; $30,000 depreciation.
- Parent 2: $180k salary + $120k bonus = $300,000 Form 1040 Line 1a, Head of Household.
- Both parents 50/50 timeshare. One child. No §4062 add-ons. No stipulated cap.

**Engine derivation for P1:**

```
schedule_e_taxable = 200,000 − 40,000 − 50,000 − 30,000 = 80,000     (federal/state see this)
court_rental       = max(0, 200,000 − 40,000 − 50,000) = 110,000    (§4058; depreciation added back)
taxable_income     = 1,080,000 + 80,000                = 1,160,000
court_total_income = 1,080,000 + 110,000               = 1,190,000

federal_tax(1,160,000, single) ≈ $381,986
ca_state_tax(1,160,000, single) ≈ $123,393
fica(1,080,000 wages, single)   ≈ $34,033          # rental excluded
niit(80,000, 1,160,000−200,000) ≈ 80,000 × 0.038 = $3,040
total_tax                       ≈ $542,452

P1 annual NDI = 1,190,000 − 542,452 − 0 (§4059) = $647,548
P1 monthly NDI ≈ $53,962
```

**Engine derivation for P2 (no rental):**

```
P2 annual NDI ≈ $196,837 (as v3.1 baseline)
P2 monthly NDI ≈ $16,403
```

**§4055 application:**

```
TN = 53,962 + 16,403 = 70,365
HN = 53,962 (P1 high earner)
H% × TN = 0.5 × 70,365 = 35,182
HN − H%·TN = 53,962 − 35,182 = 18,780
K = 0.12 + 800/70,365 ≈ 0.1314
CS = 0.1314 × 18,780 × 1.0 ≈ $2,467/mo  ≈ $29,604/yr
```

**Comparison vs. wage-only baseline:** Adding $110k of court-cognizable rental cash flow raised P1's obligation from $2,113/mo → ~$2,467/mo (~$354/mo, $4,250/yr). The increase is modest because the §4055 K-factor is in its high-NDI asymptotic regime (K → 0.12).

**Depreciation tax benefit observed:** P1 reports $80k of Schedule E taxable income to the IRS (paying tax on that), but the court attributes the full $110k pre-depreciation amount as income. The $30k depreciation reduces P1's tax bill by roughly $30k × 53.1% = $15,930, which slightly raises P1's NDI relative to a hypothetical world without depreciation — and that NDI-raising effect does flow through into a small increase in the §4055 result. Net: the parent retains most of the depreciation tax benefit while still being charged for the underlying cash flow.

## 6. V3+ Backlog

* Schedule C (self-employment) — separates earned income from wages; full self-employment tax (15.3%); business-expense scrutiny.
* K-1 (partnership / S-corp) — cash distributions vs. K-1 taxable income; basis tracking.
* Schedule D (capital gains) — distinguishing recurring vs. one-time; long-term vs. short-term treatment.
* Per-property line-item Schedule E breakdown.
* Smith-Ostler bonus split — base guideline + percentage of variable comp (per *Ostler & Smith*, 1990).
* Multi-state filing — non-CA state taxes for parents working remotely from other jurisdictions.
* Spousal support integration — CS computed first, then spousal on income net of CS.

## 7. Test Strategy

| Layer | Required Coverage |
|---|---|
| Unit — tax | Federal brackets, CA brackets, FICA caps, Additional Medicare, NIIT thresholds, PAL loss disallowance. |
| Unit — engine | K-factor brackets, child multiplier, symmetry, sign inversion, cap, depreciation add-back enforcement, FICA-not-applied-to-rental, STR FICA flag. |
| Integration — workflow | End-to-end attested baseline pivot with mixed wage+rental case. |
| Property — invariants | `court_income ≥ schedule_e_taxable` whenever depreciation > 0; `NDI` increases monotonically with gross rents holding all else equal; symmetric outputs under parent swap. |
