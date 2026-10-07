---
name: business-checking-referral-assessment
description: Assess and explain business checking referral bonus options, including referrer tenure, deposit thresholds, annual and rolling limits, and unresolved eligibility prerequisites. Use for informational referral questions and recommendation requests; it does not submit referrals or open accounts.
---

# Business Checking Referral Assessment

Use this Skill to provide an accurate, conditional assessment of business-checking referral bonuses. It ranks only the programs whose **numeric** requirements are met and clearly separates confirmed facts from conditions that still need verification.

## Scope and safety

This is an informational workflow, not a banking action. Do not create a referral, open an account, alter a profile, or imply that a bonus has been approved. If the request changes into such an action, follow all applicable banking controls first: verify identity, authority, account ownership, product eligibility, balances or credit, fees, limits, cutoffs, recipient details, and confirmation requirements.

Before giving referral recommendations or terms, check whether the referrer appears eligible to submit referrals. At minimum, obtain a reliable referrer identifier, their earliest checking-account opening date, and their referral history. Do not infer an exact tenure threshold from an imprecise date.

## Runtime information-gathering workflow

1. Identify the referrer using the customer-provided identifier. For an email address, use `get_user_information_by_email`; use the corresponding name or ID lookup only when appropriate. Do not reveal unnecessary personal data in the reply.
2. Use `get_referrals_by_user` for the identified user. Count only successful referral bonuses when evaluating the universal rolling limit. A blank result supports zero known referrals but does not establish facts about the referred business.
3. Obtain the current timestamp with `get_current_time` and the **exact** opening date of the referrer's earliest Rho-Bank checking account. Tenure is measured from the earliest checking account, not the currently held product.
4. Ask for, or otherwise verify where authorized, the proposed deposit and whether it is new money. Also assess the referred party's eligibility. An unverified fact must be reported as unresolved, not assumed true.
5. Run `scripts/assess_referral.py` with the collected facts. The script is deterministic and performs no banking action.
6. Reply with the highest potential bonus, all applicable product options, and the remaining conditions. If a prerequisite is unknown, say that the amount is conditional rather than saying the user qualifies or will receive it.

### Referred-party facts that must be confirmed

For a business referral to qualify, confirm all applicable items:

- The referred party is at least 18 years old and is a new Rho-Bank customer with no existing checking or savings account and no account closed in the prior 12 months.
- The referrer and referred party have different registered addresses.
- The referred business has a different primary owner, based on the primary authorized signer's SSN, from every existing Rho-Bank business account.
- The qualifying deposit is new money, not a transfer from another Rho-Bank account, and is made within the product's deposit window.
- The deposit remains for at least 30 days after the qualifying period ends; both accounts remain in good standing; no other new-account promotion is combined; and only one referral code is used.
- If the referred party is opening a business checking account, the opening prerequisites must separately be checked: verified customer, at least one OPEN personal checking account, at least $500 in the existing checking account, no CLOSED accounts, and fewer than six business checking accounts.

A customer can refer to a product different from their own. Do not treat the referrer's product as a restriction.

## Program schedule

| Product | Referrer bonus | Deposit requirement | Deposit window | Referrer tenure | Annual maximum |
|---|---:|---:|---:|---:|---:|
| Sky Blue | $150 | $10,000 | 90 days | 45 days | 8 |
| Cobalt Blue | $150 | $7,500 | 90 days | 60 days | 10 |
| Navy Blue | $100 | $5,000 | 90 days | 60 days | 10 |
| Hunter Green | $175 | $10,000 | 90 days | 60 days | 10 |
| Lime Green | $200 | $15,000 | 90 days | 90 days | 12 |
| World Blue | $300 | $25,000 | 90 days | 90 days | 12 |
| True Blue | $350 | $50,000 | 120 days | 90 days | 15 |
| Beige Account | $500 | $100,000 | 120 days | 120 days | 15 |

Universal limits apply across all checking products: at most two referral bonuses in a rolling nine-day period. A third bonus in that period is automatically denied and cannot be reinstated during the same window. Product annual limits also apply.

## Script interface

Run `scripts/assess_referral.py`. It reads one JSON object from standard input and writes one JSON object to standard output.

### Input schema

```json
{
  "as_of_date": "YYYY-MM-DD",
  "as_of_timestamp": "ISO-8601 timestamp with timezone, optional unless bonus_timestamps is supplied",
  "first_checking_opened": "YYYY-MM-DD or null",
  "planned_deposit": 0,
  "bonus_timestamps": ["ISO-8601 timestamps for successful bonuses across all products"],
  "annual_bonus_counts": {"World Blue": 0},
  "conditions": {
    "referred_new_customer": true,
    "referred_at_least_18": true,
    "different_address": true,
    "different_primary_owner": true,
    "qualifying_new_money": true,
    "deposit_made_within_window": true,
    "deposit_held_required_period": true,
    "no_other_promotion": true,
    "one_referral_code": true,
    "both_accounts_good_standing": true,
    "referred_verified": true,
    "referred_open_personal_checking": true,
    "referred_personal_balance_at_least_500": true,
    "referred_no_closed_accounts": true,
    "referred_business_count_under_6": true
  }
}
```

Each condition is optional and may be `true`, `false`, or `null`. Omitted and `null` values are treated as unknown. `bonus_timestamps` must contain only actual successful-bonus timestamps; use an empty list when the referral lookup confirms none. `annual_bonus_counts` is per product and should be supplied only when its values are known.

The output includes a product-by-product assessment, rolling-limit state, unknown or failed prerequisites, `best_numeric_candidate`, and `best_potential_candidate`. The latter is the highest-paying product not ruled out by supplied deposit data or another known blocker; it may still have unknown prerequisites. Neither candidate is a bonus approval.

### Runnable call example

```sh
python3 scripts/assess_referral.py <<'JSON'
{"as_of_date":"2026-01-15","first_checking_opened":"2025-09-01","planned_deposit":30000,"bonus_timestamps":[],"annual_bonus_counts":{"Sky Blue":0,"Cobalt Blue":0,"Navy Blue":0,"Hunter Green":0,"Lime Green":0,"World Blue":0,"True Blue":0,"Beige Account":0},"conditions":{}}
JSON
```

## Validation and response construction

- Confirm the script returns all eight products and no `error` field.
- Check that a product with a required deposit greater than `planned_deposit` is marked `no` for `deposit_state`.
- Check that missing first-opening date or missing referral history produces `unknown`, not a favorable eligibility assertion. In that case, use `best_potential_candidate` only to explain the highest option not ruled out; call it conditional rather than eligible.
- Treat any `false` condition, an exceeded annual maximum, a full rolling window, insufficient deposit, or insufficient tenure as a blocker.
- Treat every `unknown` condition as a reason to describe the result as conditional.
- A known empty referral history can support a zero rolling count and zero annual counts; otherwise, do not assume annual or rolling capacity. Only COMPLETE/successful bonuses count toward those limits, not applications or in-progress referrals.

In the final reply, lead with the largest **potential** bonus based on confirmed numeric facts. Then state the qualifying deposit, deposit window, and referrer tenure for each option the customer asked about. Explicitly identify deposit-too-low products and unresolved referral or opening prerequisites. State that an approximate first-opening date cannot formally establish any exact tenure threshold; it may be described only as context, never as proof. Do not promise a referral bonus or imply that an account can be opened or a referral submitted through this informational workflow.