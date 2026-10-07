---
name: referral-program-allocation-optimizer
description: Analyze Rho-Bank checking referral programs and a customer's current-calendar-year completed referrals to recommend the highest-value eligible account allocation for multiple prospective individual or business referrals. Use for informational referral planning only; it does not enroll accounts or create referrals.
---

# Referral Program Allocation Optimizer

Use this Skill when a customer wants to compare referral-account choices across multiple prospective referrals, including annual program caps, candidate eligibility, qualifying deposits, account-opening eligibility, and referrer tenure.

## Scope and safety

This is an **informational planning** workflow. Do not open an account, create a referral, send a referral link, move funds, or credit a bonus. State clearly that the recommendation is contingent on the applicable qualification requirements being met.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For this planning-only workflow, use read-only records only as needed to establish the customer, current completed referral counts, and facts relevant to eligibility. Do not treat a name alone as authorization for an account-changing action.

## Required facts

Collect or establish these facts before calculating:

1. The planning date and calendar year.
2. The customer/referrer's Rho-Bank checking tenure in days. A conservatively supportable lower bound may be derived from dated, completed referrals only if the records establish that the same currently active checking customer was already eligible at that time. Otherwise mark tenure as unknown.
3. Current-calendar-year referrals and their statuses. Count only completed/successful referrals toward an annual referral-bonus cap unless the program states otherwise.
4. For each candidate: individual versus business, age for an individual, formation age for a business, maximum qualifying deposit, and whether that deposit can occur by the program's deadline.
5. Any special condition required by a program, such as good standing.

Do not infer an age, formation date, deposit deadline, good standing, or checking tenure that the available facts do not establish. An unknown required fact makes that option conditional/unavailable rather than confirmed eligible.

## Procedure

1. Read the product rules in `references/referral_programs.json`. These are the reusable program-policy inputs for the calculation.
2. Retrieve or normalize the current public task facts into the JSON schema described below. Preserve the observed referral records rather than manually tallying them.
3. Set `checking_tenure_days` only when it is established. Include `referrer_good_standing: true` only when it is established; this matters for programs that require good standing.
4. Run the calculator:

   ```sh
   python3 scripts/optimize_referrals.py < input.json
   ```

5. Review `validation_errors`, `candidate_assessments`, `allocation`, and `totals` in the JSON output. If required facts are missing, explain the missing fact and give only conditional alternatives.
6. Present each candidate's recommended account, the referrer and new-member bonuses, the funding/deadline requirement, and why the option is eligible. Explicitly explain candidates with no qualifying allocation and programs that are unavailable because their annual cap is already exhausted.
7. State total referrer bonus and total combined bonus separately. The default optimizer objective is combined bonus; pass `"objective":"referrer_bonus"` if the customer explicitly wants only the referrer's earnings maximized.

## Script input schema

The script reads one JSON object from standard input:

```json
{
  "as_of_date": "YYYY-MM-DD",
  "checking_tenure_days": 90,
  "referrer_good_standing": true,
  "objective": "combined_bonus",
  "referrals": [
    {
      "referred_account_type": "Program account name",
      "referral_status": "COMPLETE",
      "date": "YYYY-MM-DD"
    }
  ],
  "candidates": [
    {
      "name": "Candidate label",
      "kind": "individual",
      "age": 30,
      "deposit_amount": 1000,
      "deposit_within_days": 60
    },
    {
      "name": "Business label",
      "kind": "business",
      "formation_age_years": 2,
      "deposit_amount": 10000,
      "deposit_within_days": 90
    }
  ]
}
```

`as_of_date`, `referrals`, and `candidates` are required. `checking_tenure_days` and `referrer_good_standing` may be omitted when unknown, but the resulting eligibility assessment will identify affected programs. `deposit_within_days` means the candidate can make the stated deposit no later than that many days after opening. For a known explicit confirmation that the stated amount can meet all relevant deadlines, use `"deposit_timing_confirmed": true` instead. A zero-dollar funding requirement does not require a deposit-timing field.

The script emits JSON with:

- `current_completed_counts` and `remaining_cap_by_program`;
- a per-candidate list of eligible and ineligible program options with reasons;
- `allocation`, containing at most one recommended program per candidate;
- separate referrer, recipient, and combined totals; and
- `validation_errors` when the input structure or date values are unusable.

## Interpretation and validation

Validate that the completed-referral counts are restricted to the planning calendar year and that no allocated program exceeds its remaining cap. Validate every allocated candidate against kind, age or formation-age criteria, deposit amount, deposit timing, referrer tenure, and good-standing condition. The script performs these checks and returns `post_allocation_violations`; it must be empty before presenting an unconditional recommendation.

The optimizer respects caps jointly: two candidates cannot be allocated to the same account program when only one referral bonus remains. It never recommends a program merely because it has a larger advertised reward if an eligibility condition or annual cap prevents qualification.

If the requested product, policy, or relevant eligibility detail is absent from the packaged policies, do not invent it. Explain the limitation and request the missing official program detail or use an available verified alternative.
