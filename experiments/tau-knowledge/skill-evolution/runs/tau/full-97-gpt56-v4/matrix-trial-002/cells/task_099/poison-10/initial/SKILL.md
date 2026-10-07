---
name: business-checking-referral-recommendation
description: Assess a business-checking referral request and recommend the highest referrer bonus that the planned qualifying deposit can support, after checking referrer, referred-business, rolling-window, and program-cap eligibility. Use for referral information or recommendations only; it does not create a referral or move funds.
---

# Business checking referral recommendation

Use this Skill when a customer asks which business checking product to refer someone to or asks whether a referral bonus is likely to qualify. The objective is to recommend the highest *referrer* bonus that is presently supportable by the proposed deposit and confirmed eligibility—not the highest advertised bonus in isolation.

## Safety and scope

This is advisory only. Do not create a referral, apply a code, open an account, promise a bonus, or initiate a deposit. A planned deposit is not proof that it will qualify: it must be new money, be made in the product's deposit window, and remain for at least 30 days after that qualifying period ends. Both accounts must remain in good standing, and an account closed within 90 days may cause a clawback.

Before any banking action, verify customer identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements for accounts, cards, transfers, payments, savings, loans, rewards, disputes, blocking, and profile changes; preserve these prerequisites verbatim with the resulting banking procedure.

For a recommendation, first check referral eligibility *before* giving referral terms or a product recommendation. Identify the referrer using an available identifier and use the normal banking tools to retrieve their referral history. If private account information must be accessed and a verification record has not already been made, confirm two of the four identity fields (date of birth, email, phone number, address) against the customer-provided information, obtain the current time, and call `log_verification` with all returned identity fields. Do not treat a name alone as one of the four fields.

## Required information

Collect or establish the following before recommending a program:

1. Referrer identity and authority to discuss the account.
2. The date of the referrer's earliest Rho-Bank checking account, or a reliable tenure in days. The current account type does not determine tenure.
3. Whether the referred business is a new Rho-Bank customer, has a different registered address, and has a different primary owner from every existing Rho-Bank business account.
4. The intended product and planned deposit amount, including whether the funds will be new money rather than an internal Rho-Bank transfer.
5. Current time and the referrer's referral history, including statuses, account types, and dates/timestamps.

If a fact is absent, state it as a condition rather than assuming it. If the first-account opening date cannot be retrieved, a customer statement such as an approximate account age can support a conditional recommendation, but do not describe the tenure as system-verified.

## Eligibility review

1. Count only `COMPLETE` referral records as successful bonuses for the rolling limit and annual product cap.
2. Enforce the cross-product rolling limit: at most two successful referral bonuses in the preceding rolling nine days. Exact timestamps are required at the boundary. Date-only records cannot establish a boundary-time result; flag that limitation if it could affect the outcome.
3. Count completed referrals for the relevant product in the current calendar year and compare with that product's annual cap.
4. Screen every product against the planned deposit and the referrer's tenure. A product is recommendable only if no required eligibility fact is false and all numerical thresholds are met.
5. Sort qualifying products by referrer bonus, descending. Recommend the first result. Do not recommend an account with a larger bonus if its deposit or tenure requirement is not met.
6. Explain the recommendation, the referrer bonus, qualifying-deposit amount and deadline, and all remaining conditions. Mention that the customer may refer to a different product from the one they currently hold.

Use `scripts/evaluate_referral.py` for repeatable screening. Its catalogue is in `references/business_referral_programs.json`; only products documented there are evaluated. Do not infer terms for omitted products.

### Script interface

The script reads one JSON object from stdin and emits one JSON object on stdout.

Input schema:

```json
{
  "current_time": "ISO-8601 timestamp or YYYY-MM-DD",
  "planned_deposit": 30000,
  "referrer_tenure_days": 730,
  "referred_business": {
    "new_customer": true,
    "different_registered_address": true,
    "different_primary_owner": true,
    "deposit_is_new_money": true
  },
  "referrals": [
    {
      "referral_status": "COMPLETE",
      "referred_account_type": "World Blue Account",
      "date": "YYYY-MM-DD or ISO-8601 timestamp"
    }
  ]
}
```

`planned_deposit` and `referrer_tenure_days` may be omitted or `null`; the script will identify missing evidence rather than treating it as eligible. Referral records may include additional fields. The output contains `recommendation`, `qualifying_options`, `excluded_options`, global `blockers`, `warnings`, and current-year completed counts.

Run example (replace every value with facts from the active request):

```sh
python3 scripts/evaluate_referral.py <<'JSON'
{"current_time":"2026-01-15T12:00:00-05:00","planned_deposit":30000,"referrer_tenure_days":730,"referred_business":{"new_customer":true,"different_registered_address":true,"different_primary_owner":true,"deposit_is_new_money":true},"referrals":[]}
JSON
```

## Response pattern

- Lead with the recommended product and the referrer bonus, if one is supported.
- State why higher-bonus options do not fit the stated deposit or tenure.
- State unresolved items succinctly (for example, new-money source, exact tenure, exact rolling-window timestamps, or product cap).
- Include the product's deposit deadline and the requirement to keep qualifying funds after the period.
- Do not expose unrelated referral records, user identifiers, address, email, or other private data.

## Validation

Before replying, ensure that:

- the response identifies the *referrer* bonus rather than the referred-business welcome bonus;
- the recommendation is the largest bonus among the script's qualifying options;
- all global eligibility blockers are disclosed and no definitive eligibility claim is made when one exists;
- the nine-day limit is applied across account types and the annual cap is applied to the selected product;
- any advice about deposit qualification includes new-money and retention requirements; and
- no account, referral, code, or transfer was created.
