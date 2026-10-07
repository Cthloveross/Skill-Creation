---
name: checking-referral-recommendation
description: Assess checking-account referral eligibility and recommend the highest combined referral bonus that can qualify for a proposed deposit. Use for informational referral comparisons; it does not submit, create, or modify referrals.
---

# Checking Referral Recommendation

Use this Skill when a checking customer asks which referral account/product gives the best combined referrer and new-customer bonus, or asks whether a proposed referral is likely to qualify.

## Scope and safety

This is an informational workflow only. Do **not** create a referral, apply a code, change an account, or imply that a bonus is guaranteed. Any such banking action must use the normal banking tools and, before it is taken, verify customer identity, authority, account ownership, product eligibility, applicable balances or funds, fees, limits, cutoffs, recipient details, and required confirmation.

Program policy requires checking referrer eligibility **before** giving referral recommendations. If material eligibility facts are unknown, ask for them rather than recommending an account.

## Required runtime facts

Collect or establish the following before running the evaluator:

1. A customer identifier. For an existing customer, use a read-only lookup such as `get_user_information_by_email`, `get_user_information_by_id`, or `get_user_information_by_name` to obtain the user ID. This lookup is not identity verification for a banking action.
2. The current time, using `get_current_time`.
3. The referrer's referral history, using `get_referrals_by_user`.
4. The date their **first** Rho-Bank checking account was opened, or a clear confirmation that their tenure meets the relevant threshold. Tenure is based on the earliest checking account, not the product being recommended.
5. The proposed deposit amount and whether it is new money rather than a transfer from another Rho-Bank account.
6. Confirmation that the proposed customer is new (no current account and no closed account in the past 12 months), is at a different registered address, and is at least 18. For Light Green, establish its special age/guardian eligibility instead.
7. Whether another new-account promotion or referral code will be used. A referral cannot be combined with another sign-up promotion, and only one referral code can apply.

Treat a customer's statement about another person's eligibility as an unverified representation. State the remaining conditions the referred person must satisfy; do not request unnecessary personal information about that person.

## Evaluate eligibility

Build the JSON input described in `scripts/rank_referral_programs.py` and run it with the packaged script. The program catalog is in `references/checking_referral_programs.json`; use it as the supplied product-policy catalog unless current task inputs provide an updated catalog.

A normal invocation is:

```sh
python3 scripts/rank_referral_programs.py < assessment.json
```

The script reads one JSON object from standard input and emits one JSON object to standard output. It never calls bank tools or performs bank actions.

### Input schema

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "planned_deposit": 0,
  "referrer": {
    "tenure_days": 0,
    "identity_confirmed": true,
    "current_referrals": [
      {"status": "COMPLETE", "timestamp": "ISO-8601 timestamp or YYYY-MM-DD"}
    ],
    "annual_completed_bonus_count": 0
  },
  "referred_person": {
    "new_customer_confirmed": true,
    "different_address_confirmed": true,
    "adult_confirmed": true,
    "age": null,
    "light_green_guardian_eligible": null,
    "new_money_confirmed": true,
    "no_other_new_account_promotion_confirmed": true,
    "one_referral_code_confirmed": true
  },
  "programs": null
}
```

`programs` is optional. When omitted or null, the packaged catalog is used. To use revised public terms, pass an array with the same fields as a catalog program. Use exact timestamps for completed bonuses whenever available. A date-only referral within the prior nine calendar dates is deliberately marked uncertain, because the nine-day policy is timestamp-based.

### Interpret the result

- `blocking_general_conditions` means do not make a product recommendation. Ask only for the listed missing or failed facts, or explain the known ineligibility.
- `rolling_window` reports completed bonuses in the prior rolling nine days. Two such bonuses mean the user must wait; a date-only ambiguous record needs exact timing before a conclusion.
- `eligible_ranked` contains products whose known requirements pass, sorted by combined bonus descending. Select the first record only when `recommendation` is present.
- `needs_confirmation` records are not qualified recommendations. Explain exactly what condition is missing, such as an age requirement or tenure confirmation.
- `ineligible` records explain why a higher-bonus product cannot qualify for the proposed deposit or known facts.

## Give the customer a precise response

Once eligibility is established, state:

1. The recommended product and the combined bonus, separating the referrer and new-member amounts.
2. Why it is the highest currently qualifying option for the stated deposit and tenure.
3. The critical conditions: required new-money deposit and deadline, referrer tenure, new-customer and separate-address rules, no promotion stacking/one code, and account-good-standing/retention requirements.
4. Any applicable referral cap or wait. Count only `COMPLETE` referrals as paid/earned bonuses; `IN_PROGRESS`, `APPLIED`, and `NO_PROGRESS` are not paid bonuses.
5. Material alternatives only when useful, with the concrete reason they do not qualify (for example, deposit shortfall or unestablished age eligibility).

Never describe a referral as COMPLETE until the new account opens and all program conditions are met. Explain that qualifying funds must remain for at least 30 days after the qualifying period ends, and that an account closed within 90 days may cause a bonus clawback.

## Validation checklist

Before responding, confirm that:

- the recommendation came from `eligible_ranked`, not `needs_confirmation`;
- combined bonus equals referrer bonus plus referred-person bonus;
- the planned deposit meets the selected product's threshold and deadline is stated;
- tenure is measured from the first checking relationship;
- rolling-cap analysis uses only completed bonuses and handles uncertain timestamps conservatively;
- no action was taken and no bonus was promised.
