---
name: business-referral-recommendation
description: Assess eligibility and recommend the highest referrer-bonus business checking referral program that fits a prospective business's planned qualifying deposit. Use for informational referral comparisons; do not create referrals or make account changes.
---

# Business referral recommendation

Use this Skill when a checking customer asks which business account/referral program gives them the largest **referrer** bonus and provides (or can provide) the prospective business's planned deposit.

## Scope and safety

This is an informational workflow. Do not create a referral, open an account, apply a promotion, change account data, or promise a bonus. If a later request asks for a banking action, follow the applicable banking procedure and first verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

Before giving referral recommendations or terms, determine whether the referrer can participate. The general referral policy requires this ordering because recommendations to an ineligible referrer should not be given.

## Required runtime inputs

Collect only the information needed for the comparison:

1. Planned qualifying deposit amount and the desired product type (business referral).
2. A referrer identifier (email or user ID) so the normal read-only user lookup and referral-history tools can be used.
3. Confirmation that the prospective business is new to the bank, has a different registered address, has a different primary owner from any existing bank business account, and that its primary owner meets the applicable age rule (normally 18 or older).
4. Confirmation or authoritative record of the referrer's checking tenure, measured from the earliest checking-account opening.
5. Current time and the referrer's referral history, including statuses and timestamps.

For an identity-sensitive follow-up or any action, independently verify the customer using two of the supported identity fields and log verification only after successful verification. An email lookup alone is not identity verification.

If a required fact is absent, ask a focused question. Do not infer that an LLC is new, differently owned, differently addressed, or that a reported deposit is new money. Explain that the qualifying deposit must be new money, not a transfer from another bank account, and must remain for the required holding period where the program policy requires it.

## Eligibility review

Use the normal banking read-only tools, not scripts, to retrieve the user record, current time, and referral history. Then assess and state any applicable blockers:

- Referrer tenure must meet the selected program's threshold, based on the earliest checking account, not the current account product.
- The prospective business must be a new customer, use a different registered address, and have a different primary owner; its primary owner must satisfy the age rule.
- Check for two successful referral bonuses within the preceding rolling nine-day period across all checking products. The policy uses exact timestamps. If only dates are available, do not claim a boundary-time result as certain; identify the earliest time at which the result can be confirmed or ask for timestamps.
- Check the selected program's calendar-year cap using the scope stated in that program's governing terms. Do not assume that a cap is global across products unless the terms say so.
- A referral bonus cannot stack with a new-account promotion or another referral code. Both accounts must remain in good standing; early closure and failure to maintain a qualifying deposit can result in no payment or a reversal.

A referral shown as `COMPLETE` is a successful bonus for rolling-window/cap counting. Do not count `IN_PROGRESS`, `NO_PROGRESS`, `APPLIED`, `REJECTED`, or `ERROR` as successful unless an authoritative program rule says otherwise.

## Compare eligible products

From the authorized product terms, create one offer object per business program containing the product name, referrer bonus, qualifying deposit, deposit window, referrer-tenure days, annual cap, and annual-cap scope. Include only programs whose required deposit is no greater than the planned deposit and whose tenure is satisfied. Account-type matching is not required: a customer may refer a business to another checking product if their earliest-checking tenure qualifies.

Use `scripts/recommend_referral.py` to make ranking and history-counting deterministic. It receives JSON on standard input and emits JSON on standard output; it does not call bank tools or cause any banking action.

### Script input schema

```json
{
  "as_of": "YYYY-MM-DDTHH:MM:SS±HH:MM",
  "planned_deposit": 30000,
  "referrer_tenure_days": 100,
  "base_eligibility": {
    "new_customer": true,
    "different_address": true,
    "different_primary_owner": true,
    "age_eligible": true,
    "new_money_confirmed": true,
    "no_conflicting_promotion": true,
    "good_standing_confirmed": true
  },
  "offers": [
    {
      "name": "Product name",
      "referrer_bonus": 0,
      "qualifying_deposit": 0,
      "deposit_window_days": 0,
      "tenure_days": 0,
      "annual_cap": 0,
      "annual_cap_scope": "program",
      "program_keys": ["Product name"]
    }
  ],
  "referrals": [
    {"status": "COMPLETE", "date": "YYYY-MM-DDTHH:MM:SS±HH:MM", "referred_account_type": "Product name"}
  ]
}
```

`annual_cap_scope` is `program` when only matching `program_keys` count, or `global` only if the governing terms explicitly impose a cross-program annual cap. A referral date without a time is accepted for calendar-year caps but makes rolling-nine-day eligibility `unknown` whenever it might affect the result.

### Script output schema

The output has `base_eligibility`, `rolling_window`, `offers`, and `recommendation`. Each offer has `eligible`, `blockers`, cap count, and a numeric bonus. `recommendation` is the eligible offer with the largest referrer bonus, with a deterministic name tie-breaker, or `null` when none is eligible. Treat `unknown` rolling-window status as a blocker until exact timestamps resolve it.

Example executable call (replace all values with current task data):

```sh
python3 scripts/recommend_referral.py <<'JSON'
{"as_of":"2025-01-01T12:00:00-05:00","planned_deposit":30000,"referrer_tenure_days":100,"base_eligibility":{"new_customer":true,"different_address":true,"different_primary_owner":true,"age_eligible":true,"new_money_confirmed":true,"no_conflicting_promotion":true,"good_standing_confirmed":true},"offers":[],"referrals":[]}
JSON
```

## Respond to the customer

If a recommendation exists, plainly name the selected account, state the referrer's bonus (not the referred business's welcome bonus), and explain why higher-paying products do not fit the stated deposit or eligibility. Include the selected program's deposit amount and deadline, referrer-tenure threshold, annual cap, and the material general conditions above. State that the referral is contingent on successful account opening, qualifying new-money deposit, the required holding period, good standing, and no incompatible promotion.

If the customer is blocked by a cap or rolling window, say that no currently eligible recommendation can be made and give the relevant wait/next-check information if exact timestamps support it. If facts are incomplete, request only the missing facts instead of ranking products. Never expose unrelated customer data, internal IDs, or full referral history in the customer-facing reply.

## Validation

Before relying on the script output, ensure every offer has nonnegative monetary amounts and day counts, ISO-8601 `as_of`, and a nonempty name. Reject malformed input rather than silently treating it as eligible. Confirm that the response's stated bonus equals `recommendation.referrer_bonus`, the selected qualifying deposit does not exceed the planned amount, all selected-program blockers are empty, and the rolling-window status is `eligible`.
