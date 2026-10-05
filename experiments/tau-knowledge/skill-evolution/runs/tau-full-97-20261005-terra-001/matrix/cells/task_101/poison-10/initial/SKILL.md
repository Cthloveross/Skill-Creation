---
name: checking-referral-eligibility-and-optimization
description: Assess whether a Rho-Bank checking customer may submit referrals, then recommend the highest combined referrer-and-new-customer referral options only after all mandatory eligibility, annual-cap, and rolling-window checks are confirmed. Use for informational referral planning; it does not submit a referral or perform banking actions.
---

# Checking Referral Eligibility and Optimization

Use this skill for a customer seeking referral eligibility, referral-program details, or the best referral-account choice. The required order is important: **check the referrer's eligibility before giving recommendations or referral terms.** Do not send a referral, apply a code, or promise a bonus.

## Scope and assumptions

The packaged catalog covers the checking referral programs supported by the supplied knowledge. `combined_bonus` means the stated referrer bonus plus the stated referred-party welcome bonus. It is a comparison value, not a guarantee of payment.

The referrer-tenure threshold is always measured from the opening date of the customer's **earliest Rho-Bank checking account**, regardless of the customer's current product. A customer may refer someone to a different account type if the threshold is met.

## Required workflow

1. **Identify the customer before customer-specific lookup.** If account/referral history must be retrieved, obtain and confirm two of date of birth, email, phone number, and address; then log verification using the available verification procedure. Use only authorized read-only customer and referral-history tools.
2. **Collect or retrieve referrer prerequisites before discussing programs or recommending accounts:**
   - earliest Rho-Bank checking opening date;
   - successful/`COMPLETE` referrals and their exact timestamps, account types, and dates in the current calendar year;
   - intended referral timing;
   - confirmation that the customer has fewer than two successful bonuses in the immediately preceding rolling nine-day interval.
3. **Determine whether the referrer can participate.** Check candidate account tenure, its annual cap, and the universal rolling nine-day cap. Count referrals across all checking products for the rolling cap. A third successful referral in a rolling nine-day window is automatically denied and cannot be reinstated in that window. Use exact timestamps when available; date-only history cannot establish a boundary case.
4. **If any referrer prerequisite is missing or cannot be confirmed, stop.** State that eligibility and an optimal recommendation cannot yet be determined. Request the specific missing information or use the available authorized lookup. Do not rank programs, quote account-specific bonuses, or present a referral recommendation before this gate passes.
5. **After the referrer gate passes, check every proposed referred party:**
   - must be a new Rho-Bank customer with no existing checking, savings, or closed Rho-Bank account in the preceding 12 months;
   - must have a different registered address from the referrer (individual referrals);
   - must meet product age eligibility; Light Green is the exception that may serve a minor with a guardian, while its primary holder must be 13–24;
   - for businesses, the primary authorized signer/primary owner SSN must differ from any existing Rho-Bank business-account primary owner;
   - must meet the selected product's stated qualification/deposit conditions and any documented product eligibility (for example, Sky Blue startup formation requirement).
6. Run `scripts/referral_advisor.py` with confirmed facts. It returns eligibility blockers, feasible product options, cap usage, scheduling warnings, and a selection that maximizes aggregate combined bonuses subject to annual capacities. Review its `data_gaps`, `warnings`, and `requires_manual_confirmation` before relying on a selection.
7. When making a business-account recommendation during November 2025, apply the documented promotional ordering only among options that meet **all** customer requirements: Sky Blue first, Lime Green second, then other qualifying products only if neither promotional product qualifies. Never override a stated requirement or an annual/rolling cap for promotion.
8. Explain qualification after an option is selected: qualifying deposits must be new money, not transfers from another Rho-Bank account, and must remain for at least 30 days after the qualifying period ends. Referral and other new-account/sign-up offers cannot stack; only one referral code applies per new account. Bonuses may be clawed back if the referred account closes within 90 days, and both accounts must remain in good standing.

## Referral timing and annual-cap rules

- The rolling limit is a cross-product maximum of two successful referral bonuses in any rolling nine-day window. Schedule a third only after the oldest relevant successful bonus is **more than nine days old**. Treat absent time-of-day data as unresolved at the exact boundary.
- Account-specific annual caps apply to successful referrals for that account type in the current calendar year. Do not treat `APPLIED`, `IN_PROGRESS`, `NO_PROGRESS`, `REJECTED`, or `ERROR` as a received bonus unless reliable records establish otherwise.
- A referral status of `COMPLETE` means the referred person opened and met the criteria. `IN_PROGRESS` means an account is open but its qualifying deposit is still outstanding; `NO_PROGRESS` means no application; `APPLIED` awaits a decision; `REJECTED` is denied; `ERROR` requires support or retry as appropriate.

## Script interface

Run the entrypoint as a JSON-on-stdin/JSON-on-stdout program:

```json
{
  "as_of": "2025-11-14T03:40:00-05:00",
  "referrer": {
    "first_checking_opened": "2025-01-01",
    "identity_verified": true,
    "complete_referrals": [
      {"account_type": "Blue Account", "timestamp": "2025-02-01T12:00:00-05:00", "status": "COMPLETE"}
    ]
  },
  "candidates": [
    {
      "name": "Candidate label",
      "kind": "individual",
      "age": 30,
      "planned_deposit": 1000,
      "new_customer_confirmed": true,
      "different_address_confirmed": true,
      "business_owner_different_confirmed": null,
      "startup_formation_years": null
    }
  ],
  "planned_referral_time": "2025-11-14T04:00:00-05:00",
  "apply_november_2025_business_priority": true
}
```

`kind` is `individual` or `business`. Use ISO-8601 timestamps with timezone offsets. `planned_deposit` is numeric USD. Use `null` for unknown facts rather than guessing. For a business, supply `business_owner_different_confirmed`; for Sky Blue, supply `startup_formation_years` when known. The script emits an object with:

- `referrer_gate`: pass/fail and unresolved prerequisites;
- `candidates`: candidate-specific feasibility/blocker information;
- `recommendations`: selected product/candidate pairings only if all decision-critical facts are confirmed;
- `combined_bonus_total`, `warnings`, `data_gaps`, and `requires_manual_confirmation`.

Example runnable call after placing the JSON above in standard input:

```sh
python3 scripts/referral_advisor.py < input.json
```

## Validation before responding

Confirm that the output has `referrer_gate.passed: true`, no unresolved `data_gaps`, and no candidate blockers before presenting a recommendation. Independently ensure the selected count for every product does not exceed `annual_cap - completed_this_year`, every selected deposit meets the product threshold, and no planned bonus would create three successful bonuses within nine days. If exact timestamps, customer-newness, addresses, business ownership, or earliest checking date are unavailable, frame the result as pending verification—not approved or optimal.

## Banking-action boundary

This skill provides information and planning only. If a later request seeks an actual banking/referral action, before that action verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements. Obtain required confirmation immediately before action and use the execution agent's ordinary banking tools; this script cannot cause any action.
