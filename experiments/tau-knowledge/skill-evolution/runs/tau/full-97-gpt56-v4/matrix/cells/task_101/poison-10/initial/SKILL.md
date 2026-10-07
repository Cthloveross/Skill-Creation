---
name: referral-eligibility-and-offer-planner
description: Safely assess checking-account referral eligibility and select the highest-value compliant referral account for each prospective individual or business. Use for referral-program questions, referral bonus comparisons, annual-cap checks, and rolling-window planning. It never submits a referral or makes account changes.
---

# Referral Eligibility and Offer Planner

Use this Skill to give accurate, policy-compliant referral guidance. Referral programs require eligibility screening before discussing program terms or recommending an offer.

## Safety boundary

This Skill is informational only. It does not create referrals, open accounts, apply codes, move money, or perform any banking action. If a later request requires an action, use only the declared normal banking tools and, before the action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

## Required workflow

1. **Identify and authorize access to customer-specific data.** If account-specific history or personal details must be retrieved, obtain the required identity verification first. Confirm two of the four supported identity fields (date of birth, email, phone number, address) and create the required verification log before treating private lookup results as authorized. Do not regard a name alone as identity verification.
2. **Check the referrer first.** Before stating referral terms or making a recommendation, establish the date the referrer first opened *any* Rho-Bank checking account. Tenure is calculated from that earliest checking opening, not the account currently held. If it cannot be established, explain that eligibility cannot yet be confirmed and request the date or an authorized account-history lookup; do not provide referral-offer comparisons.
3. **Collect eligibility facts for every prospective referral.** For an individual, require age, a confirmed new-customer status (no current checking/savings and no account closed in the last 12 months), confirmation that they are not registered at the referrer's address, intended deposit amount/source, and any account preference. For a business, require confirmation it is new to Rho-Bank, formation age where relevant, qualifying deposit/source, and confirmation that its primary authorized signer differs from the primary owner of every existing Rho-Bank business account.
4. **Treat missing facts as blockers, not assumptions.** A name lookup with no match is not proof of new-customer eligibility. Never infer address, account history, ownership/SSN distinction, new-money source, or age from a relationship description.
5. **Check referrer history.** Retrieve or use authorized referral history, count `COMPLETE` referrals in the calendar year by account type, and count successful bonuses in the preceding rolling nine-day interval using exact timestamps when available. A third successful bonus in any rolling nine-day window is denied across all checking products. Existing annual caps cannot be exceeded.
6. **Evaluate offers and select recommendations.** Use `references/program_catalog.json` and run the packaged planner. Recommend only candidates whose required facts are all explicitly confirmed. The planner considers individual product requirements, account-specific annual caps, referrer tenure, current business promotion priority, and total combined bonus. It does not interpret a possible bonus as guaranteed.
7. **Communicate conditions and schedule.** For each selected option, state the account, both bonus amounts, qualifying deposit and deadline, and any annual-cap availability. Explain that deposits must be new money, must remain for at least 30 days after the qualifying period, the account must remain in good standing, referral bonuses cannot stack with another new-account promotion, and early closure within 90 days can cause clawback. If more than two qualifying bonuses could occur close together, instruct the customer to ensure no more than two successful bonuses occur in any rolling nine-day period; waiting until the oldest counted bonus is more than nine days old is the safe rule.
8. **Do not submit anything.** Give the customer the applicable referral-link/dashboard or support path only when it is available in the supplied runtime or product documentation. No script output authorizes an account opening or referral submission.

## Current business-account campaign

When the evaluation date falls within a configured promotion period, business accounts that meet every stated requirement are prioritized in this order: Sky Blue, then Lime Green, then other qualifying business products. This priority never overrides eligibility, annual caps, or the customer’s stated requirements. The catalog stores the known November 2025 campaign dates; supply the actual evaluation date to the planner.

## Planner script

`scripts/plan_referrals.py` receives one JSON object on stdin and writes one JSON object to stdout. It uses the packaged catalog automatically.

### Input schema

```json
{
  "as_of": "YYYY-MM-DD or ISO timestamp",
  "referrer": {
    "first_checking_opened": "YYYY-MM-DD",
    "identity_verified": true
  },
  "candidates": [
    {
      "label": "user-facing label",
      "kind": "individual or business",
      "age": 0,
      "formation_years": 0,
      "deposit": 0,
      "new_to_rho": true,
      "same_address_as_referrer": false,
      "primary_owner_distinct": true,
      "deposit_is_new_money": true
    }
  ],
  "referrals": [
    {
      "referred_account_type": "Catalog account name",
      "referral_status": "COMPLETE",
      "date": "YYYY-MM-DD or ISO timestamp"
    }
  ]
}
```

`age` and `same_address_as_referrer` apply to individuals. `formation_years` and `primary_owner_distinct` apply to businesses. Use JSON `null` or omit a field when unknown; unknown required facts block that candidate. `referrals` may be empty. Dates must be parseable ISO-style dates.

### Output schema

The output contains `status` (`blocked`, `no_eligible_offers`, or `ready`), `referrer`, `blockers`, `recommendations`, `total_combined_bonus`, `annual_usage`, and `rolling_window`. If referrer eligibility cannot be evaluated, status is `blocked` and no program terms or recommendations are emitted. Candidate blockers identify the fact to obtain without guessing. Each recommendation includes a product, both bonuses, combined bonus, deposit condition, tenure condition, and general reminders.

### Runnable call and validation

Run through the supplied script runtime with a JSON object matching the schema, for example `run_skill_script` using relative path `scripts/plan_referrals.py`. Validate that:

- malformed or missing `as_of` returns an `error` object;
- absent referrer opening date returns `status: "blocked"` and an empty `recommendations` list;
- an unknown individual address/new-customer fact or unknown business owner-distinction fact produces a candidate blocker rather than a recommendation;
- selected recommendations do not exceed the catalog annual cap after completed referrals; and
- `rolling_window.remaining` is never below zero.

## Failure handling

- If required eligibility evidence is unavailable or out of scope, clearly say qualification and an optimal offer cannot be confirmed. Ask only for the missing facts.
- If the referrer has no available checking-history source, do not substitute referral dates or a current product for the earliest checking opening date.
- If a product or requested account is absent from the catalog, say its terms are unsupported by the available documentation rather than inventing terms.
- If source dates lack timestamps, treat rolling-window calculations as a planning warning; exact eligibility requires timestamps.
