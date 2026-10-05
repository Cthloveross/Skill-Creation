---
name: business-checking-referral-recommender
description: Evaluate which documented business checking referral program maximizes a referrer's bonus for a prospective business, after validating referrer, prospective-business, annual-cap, and rolling-window eligibility. Use for informational referral-program comparisons; it does not create or submit referrals.
---

# Business Checking Referral Recommender

Use this skill when a customer asks which business checking account to refer a business to, especially when the answer depends on the prospective deposit, referrer tenure, existing referral history, annual program caps, or the cross-program rolling referral limit.

## Scope and safety

- This skill supplies an eligibility-aware recommendation only. Do **not** create a referral, open an account, make a deposit, alter customer data, or imply that a bonus is guaranteed.
- Do not expose a customer's referral history or other private customer information until the customer has been identity-verified under the available runtime procedure.
- A referrer does not need to hold the same checking product as the product being referred. Tenure is measured from the referrer's earliest Rho-Bank checking-account opening date.
- Do not recommend a program until the referrer's eligibility has been checked. If any required fact is unavailable, state what must be confirmed rather than treating it as true.
- The referral terms modeled here are the supplied business-checking referral terms. Escalate or seek current program terms if an account type, promotion, account status, ownership question, or required qualification is unsupported by those terms.

## Runtime workflow

1. **Identify and verify the customer before personalized lookup.** Obtain a customer identifier or exact name. Use the available read-only user lookup. Ask the customer to confirm two of the four identity fields (date of birth, email, phone number, address), then log the verification with the current time using `log_verification`. Do not repeat private lookup data in the response.
2. **Collect the eligibility facts before giving a recommendation.** Confirm:
   - days since the referrer's *earliest* checking account opened and current good standing;
   - the proposed initial/qualifying deposit amount and whether it is new money;
   - the prospective business is new to Rho-Bank, with no existing account or account closed in the prior 12 months;
   - the prospective business has a different primary owner (primary authorized signer's SSN) from every existing Rho-Bank business account;
   - the prospective business is registered at a different address from the referrer;
   - the prospective business can keep the qualifying new-money deposit for at least 30 days after the relevant qualification period ends;
   - both accounts must remain in good standing;
   - the prospective account will not use another new-account promotion and will use only one referral code.
3. **Retrieve referral history** with `get_referrals_by_user` only after identity verification. Retrieve the current timestamp with `get_current_time`. The universal cap is at most two successful referral bonuses in any rolling nine-day interval across all checking account types. The evaluation must use bonus timestamps where available; a date-only record exactly on the nine-day boundary is insufficient to safely decide the cap.
4. Normalize the collected facts into the JSON schema below and run `scripts/evaluate_referral.py`.
5. If `referrer_gate.eligible_to_receive_recommendation` is false, do not name a best program. Explain the unmet, missing, blocked, or time-uncertain prerequisite and, where appropriate, the earliest need to obtain an exact completion/bonus timestamp.
6. If recommendations are returned, lead with the first result: account type, maximum referrer bonus, required new-money deposit, deposit window, and applicable tenure requirement. Mention that qualification, good standing, deposit retention, the rolling cap, and annual cap still govern payment.
7. If the customer asks to submit a referral or otherwise take a banking action, use only the execution agent's normal banking tools and recheck identity, authority, ownership, product eligibility, balances, fees, limits, recipient details, cutoffs, and any confirmation requirement before acting. This skill itself performs no action.

## Program data modeled by the evaluator

The evaluator compares only programs with sufficiently documented qualification criteria:

| Referred account | Referrer bonus | Annual cap | New-money qualifying deposit | Deposit window | Referrer tenure |
|---|---:|---:|---:|---:|---:|
| Beige | $500 | 15 | $100,000 | 120 days | 120 days |
| True Blue | $350 | 15 | $50,000 | 120 days | 90 days |
| World Blue | $300 | 12 | $25,000 | 90 days | 90 days |
| Lime Green | $200 | 12 | $15,000 | 90 days | 90 days |
| Hunter Green | $175 | 10 | $10,000 | 90 days | 60 days |
| Cobalt Blue | $150 | 10 | $7,500 | 90 days | 60 days |
| Navy Blue | $100 | 10 | $5,000 | 90 days | 60 days |

Sky Blue's stated bonus and annual limit are retained as a notice, but its supplied terms do not establish a qualifying-deposit rule or tenure requirement. It is therefore never returned as a confirmed eligible recommendation.

The annual cap is evaluated against `COMPLETE` referrals for the target program in the calendar year of `as_of`. The rolling cap uses all `COMPLETE` referrals, regardless of target program. A status other than `COMPLETE` does not count as a received referral bonus for these calculations.

## Evaluator interface

Run the packaged script with JSON on standard input and consume its JSON from standard output:

```sh
printf '%s' "$REFERRAL_FACTS_JSON" | python3 scripts/evaluate_referral.py
```

`REFERRAL_FACTS_JSON` must contain:

```json
{
  "as_of": "ISO-8601 timestamp including an offset",
  "proposed_deposit": "number",
  "referrer": {
    "identity_verified": "boolean",
    "checking_tenure_days": "integer",
    "good_standing": "boolean"
  },
  "candidate": {
    "new_customer_no_accounts_in_last_12_months": "boolean",
    "different_registered_address": "boolean",
    "different_business_primary_owner": "boolean",
    "qualifying_deposit_is_new_money": "boolean",
    "will_retain_deposit_30_days_after_qualification_period": "boolean",
    "will_remain_in_good_standing": "boolean",
    "no_other_new_account_promotion": "boolean",
    "one_referral_code_only": "boolean"
  },
  "referrals": [
    {
      "referred_account_type": "documented account type/name",
      "referral_status": "COMPLETE or another documented status",
      "bonus_timestamp": "ISO-8601 timestamp when available; otherwise date-only YYYY-MM-DD"
    }
  ]
}
```

`as_of`, `proposed_deposit`, all referrer fields, all candidate fields, and `referrals` are required. Referral records may instead use `date` in place of `bonus_timestamp`. Use a full timestamp whenever possible. The result contains input errors, a common eligibility gate, rolling-window details, program-by-program determinations, and descending eligible recommendations. Validate that the result has `ok: true` before relying on it.

## Response guidance

For a qualifying recommendation, keep the response direct: identify the highest confirmed referrer bonus that the stated deposit can qualify for, then give the deposit amount/window and any material conditions. Do not say a larger-bonus program is available unless its larger deposit and tenure conditions are actually met. If the deposit is described as approximate, explain that the qualifying threshold must actually be deposited as new money within the applicable window.

Do not disclose the contents of the evaluator's private history fields. It is sufficient to say that the referral-frequency and annual-cap checks were passed, blocked, or could not be determined from timestamp precision.
