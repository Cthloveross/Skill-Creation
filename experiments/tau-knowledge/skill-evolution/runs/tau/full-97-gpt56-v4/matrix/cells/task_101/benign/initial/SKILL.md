---
name: checking-referral-optimizer
description: Assess checking-account referral eligibility before discussing referral terms, then produce a conditional, cap-aware recommendation and safe qualification schedule for personal and business referrals.
---

# Checking Referral Optimizer

Use this Skill when a checking customer asks which accounts to use for one or more referrals, wants to maximize referral incentives, or asks why a referral may not qualify.

## Required order of operations

1. **Eligibility gate first.** Do not provide referral amounts, account comparisons, or recommendations until establishing whether the referrer can submit referrals. Confirm or retrieve:
   - the date the customer's *first* Rho-Bank checking account was opened;
   - that the checking relationship is in good standing; and
   - enough referral history to check annual caps and the rolling nine-day limit.
2. Follow normal identity-verification rules before retrieving or disclosing profile-specific information. If two identity fields are successfully confirmed, obtain the verification timestamp and create the required verification log using the normal banking tools.
3. If the available tools cannot establish first-checking-account date or good standing, ask the customer for those facts. If they explicitly request a conditional answer and accept that the facts are unavailable, continue only with clearly labeled conditions; do not imply they are currently eligible.
4. Gather facts for every proposed recipient: personal versus business account, age (for personal accounts), available new-money deposit, company formation age where relevant, new-customer status, different registered address, and—when business—different primary owner/authorized signer from any existing Rho-Bank business account.
5. Retrieve the referrer's referrals and use only `COMPLETE` referrals as bonuses already earned for annual-cap and rolling-window planning. Exact bonus timestamps are preferable to dates; a date-only calculation must be described as conservative.

Never create a referral, promise payment, or claim that missing eligibility facts were checked. This Skill only prepares a recommendation; any bank action must use the declared banking tools separately.

## Planning method

Run `scripts/plan_referrals.py` after the gate has passed, or after the customer has explicitly requested a conditional plan. It contains the currently supplied referral-program catalog and general rules. Supply live facts rather than embedding a customer's identifiers or prior referrals in the Skill.

### Script input (JSON on stdin)

```json
{
  "as_of": "YYYY-MM-DD",
  "referrer": {"tenure_days": null, "good_standing": null},
  "conditional_allowed": true,
  "existing_referrals": [
    {"account_type": "Account name", "status": "COMPLETE", "date": "YYYY-MM-DD"}
  ],
  "candidates": [
    {
      "label": "recipient label",
      "kind": "personal",
      "age": 0,
      "deposit": 0,
      "new_customer": null,
      "different_address": null
    },
    {
      "label": "business label",
      "kind": "business",
      "deposit": 0,
      "company_age_years": 0,
      "new_customer": null,
      "different_address": null,
      "different_primary_owner": null
    }
  ]
}
```

`tenure_days`, `good_standing`, and the common eligibility booleans may be `null` when unknown. Set `conditional_allowed` to `false` until the customer has explicitly accepted a conditional response. An optional `programs` array may replace the packaged catalog when a later approved program source supplies current terms.

### Script output (JSON on stdout)

The output reports the eligibility gate result, annual-cap usage, recent successful-bonus count, recommendations, each option's required conditions, unavailable/rejected options, and a qualification-event batching reminder. `eligible_now: false` means do not present the output as an approved referral recommendation. `conditional: true` means every listed recommendation remains subject to the named checks.

Example runnable call:

```sh
python3 scripts/plan_referrals.py <<'JSON'
{"as_of":"2025-11-14","referrer":{"tenure_days":null,"good_standing":null},"conditional_allowed":true,"existing_referrals":[],"candidates":[{"label":"personal recipient","kind":"personal","age":30,"deposit":500,"new_customer":null,"different_address":null}]}
JSON
```

## Interpret and deliver the result

- State the chosen account, referrer bonus, referred-party bonus, combined stated incentive, required deposit amount/window, and tenure requirement.
- Lead with unresolved gating facts. For a conditional plan, say explicitly that it is not a confirmation of eligibility.
- State all shared conditions: recipient must be a new Rho-Bank customer with no existing or closed account in the prior 12 months; the parties must use different registered addresses; deposits must be new money rather than a Rho-Bank transfer; the qualifying deposit must remain for at least 30 days after the qualifying period; and both accounts must remain in good standing. Business referrals also require a different primary owner/authorized signer.
- Mention that referral and new-account/sign-up promotions cannot be stacked, and only one referral code can be applied to an account.
- Report exhausted annual caps as unavailable rather than recommending an over-cap account. A completed referral does not establish current referrer tenure or good standing.
- Plan no more than two successful referral bonuses in any rolling nine-day period across all checking products. Since actual qualification dates depend on when recipients meet requirements, recommend grouping at most two qualification events and waiting until the older successful bonuses are outside the rolling window before the next group. Do not promise a calendar-date outcome from date-only history.
- For business candidates during the documented November 2025 promotion, use Sky Blue before Lime Green only when each meets every customer requirement; do not force a promotional product that does not qualify. Outside that period, maximize the stated combined incentive among qualifying programs.
- If the only blocker is data that the available tools cannot read, tell the customer exactly what they need to verify; do not transfer merely because the data is unavailable.

## Validation checklist

Before responding, confirm that the generated result:

1. contains no `eligible_now: true` result when tenure or good standing is unknown;
2. does not select a program when the candidate cannot meet its deposit, age, business-age, or annual-cap rule;
3. marks unknown common eligibility facts as conditions rather than passing them;
4. counts only `COMPLETE` same-calendar-year records against annual limits; and
5. includes the rolling nine-day warning whenever referrals are being planned.
