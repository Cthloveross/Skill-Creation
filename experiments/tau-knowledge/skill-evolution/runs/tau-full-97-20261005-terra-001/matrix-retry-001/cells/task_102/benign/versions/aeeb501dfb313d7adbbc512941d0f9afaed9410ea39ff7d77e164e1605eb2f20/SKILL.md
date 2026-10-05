---
name: checking-referral-eligibility-review
description: Assess whether a checking-account customer may be advised about or proceed with Gold Years, Dark Green, or Sky Blue referrals. Use when a customer asks about referral eligibility, annual limits, rolling referral caps, candidate qualification, or referral rewards.
---

# Checking Referral Eligibility Review

Use this Skill to give a precise, evidence-based referral assessment without treating unknown recipient facts as approvals or denials.

## Required gate: assess the referrer first

Before providing referral recommendations, rewards, or program-term guidance, establish whether the referrer is eligible to submit referrals for each requested program.

1. Resolve the customer using an identifier supplied by the customer and obtain their referral history and the current time using the available banking tools.
2. Establish the earliest date on which the customer became a Rho-Bank checking customer and whether the required checking relationship remains active/in good standing. The current account product does not determine tenure.
3. Apply the relevant tenure threshold: 30 days for Gold Years and 45 days for Dark Green or Sky Blue.
4. Count completed referral bonuses in the relevant calendar year for the requested program and compare them with that program's annual cap.
5. Count completed bonuses of **all** checking account types in the preceding rolling nine days. This cross-product count has a maximum of two.

Do not infer an active checking relationship from a name lookup or from the absence of data. Past completed referrals can corroborate that a customer was previously eligible, but cannot by themselves prove a currently active, good-standing checking relationship. If the required referrer facts cannot be confirmed, say that referral eligibility cannot yet be confirmed, identify the exact missing referrer facts, and do not recommend submission.

## Candidate review

Once the referrer gate is satisfied, review each target separately. A missing fact is an **unconfirmed prerequisite**, not a rejection.

All referrals require:

- The referred party is new to Rho-Bank: no existing account and no account closed within the last 12 months.
- The referrer and a personal referred customer have different registered addresses.
- The qualifying deposit is new money, not a transfer from another Rho-Bank account, and remains for at least 30 days after the qualifying period ends.
- The referral is not stacked with another new-account promotion or sign-up bonus; only one referral code is used.
- Both accounts remain in good standing. A referred account closed within 90 days may cause reversal of the bonus.

For a business referral, verify that the business's primary authorized signer does not have the same SSN as the primary owner of an existing Rho-Bank business account.

Then apply the product-specific facts:

| Program | Candidate/product eligibility | Deposit qualification | Referrer tenure | Annual cap | Referrer / candidate reward |
|---|---|---:|---:|---:|---:|
| Gold Years | Referred person is age 62 or older | $1,000 within 90 days | 30 days | 6 | $50 / $75 |
| Dark Green | Referred person opens Dark Green and is age 17 through 26 | $1,000 within 60 days | 45 days | 6 | $40 / $30 |
| Sky Blue | Business is within 4 years of formation; distinct qualifying primary owner | $10,000 within 90 days | 45 days | 8 | $150 / $250 |

The program annual cap is a cap on referral bonuses, so calculate it from `COMPLETE` referrals in the requested program during the calendar year. The rolling cap is cross-program and based on successful referral bonuses. It is evaluated at the time a bonus would be received; do not promise that a referral submitted now will have future rolling-cap capacity.

## Using the helper

Run `scripts/assess_referrals.py` with data gathered at runtime. It only performs deterministic calculations; it neither looks up banking data nor submits referrals.

### Input JSON

```json
{
  "as_of": "ISO-8601 timestamp or YYYY-MM-DD",
  "referrer": {
    "earliest_checking_opened": "ISO-8601 timestamp or YYYY-MM-DD, optional",
    "active_checking_in_good_standing": true
  },
  "referrals": [
    {
      "referred_account_type": "Gold Years Account",
      "referral_status": "COMPLETE",
      "date": "ISO-8601 timestamp or YYYY-MM-DD"
    }
  ],
  "candidates": [
    {
      "label": "optional display label",
      "account_type": "Gold Years Account | Dark Green Account | Sky Blue Account",
      "age": 62,
      "new_customer_no_account_last_12_months": true,
      "different_registered_address": true,
      "primary_owner_no_existing_rho_business_account": true,
      "formation_age_years": 3,
      "has_other_new_account_promotion": false,
      "one_referral_code_only": true
    }
  ]
}
```

Use `null` or omit a fact when it is unknown. Personal-address fields apply to Gold Years and Dark Green; business-owner and formation fields apply to Sky Blue. The script emits JSON with program capacities, the current cross-product rolling count, per-candidate checks, missing facts, and data-quality warnings.

Example invocation in an executor that supports packaged scripts:

```text
run_skill_script("scripts/assess_referrals.py", gathered_runtime_json)
```

## Interpret and respond

1. If `referrer_gate_complete` is false, lead with the unresolved referrer check. Do not state that the user can submit a referral.
2. If a program's `referrer_status` is `ineligible`, clearly name the blocker (tenure, inactive/not-good-standing relationship, or annual cap). If it is `unknown`, request or obtain only the missing verification.
3. For a candidate, distinguish `pass`, `fail`, and `unknown`. Explain that an unknown new-customer, address, or business-owner condition prevents confirmation; it does not establish ineligibility.
4. State the rolling-window result separately from annual capacity. A current opening does not reserve a future rolling slot.
5. Explain relevant qualifying-deposit, promotion-stacking, good-standing, and clawback conditions after the eligibility gate is complete.
6. Do not claim to have checked recipient account history, addresses, or business ownership unless a supported tool or supplied record actually establishes it. Do not submit, create, or alter a referral; use normal banking tools only if the runtime and task explicitly authorize an action.

## Validation

Before sending a customer-facing answer, verify that it: (a) names all missing prerequisites, (b) does not equate unknown with pass, (c) counts only `COMPLETE` records for bonus caps, (d) applies the rolling count across account types, (e) does not promise future bonus eligibility, and (f) gives no product recommendation before the referrer gate is complete. See `references/referral_policy.md` for the source-backed rules and edge cases.
