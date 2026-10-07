---
name: business-checking-referral-recommender
description: Evaluate which documented business checking referral program can maximize a referrer's bonus only after identity, referral history, and all eligibility conditions are verified. Use for informational business-referral comparisons; this skill never submits a referral or opens an account.
---

# Business Checking Referral Recommender

Use this skill when a customer asks which business checking account to refer a prospective business to, especially where the answer depends on deposit amount, referrer tenure, referral history, annual caps, or the cross-program rolling limit.

## Scope and safety

- Provide an eligibility-aware informational comparison only. Do **not** create a referral, open an account, make a deposit, change customer data, or imply a bonus is guaranteed.
- Do not disclose referral history or other private customer information until the customer has been identity-verified using the available runtime procedure.
- Do not provide account-specific referral terms or a recommendation before the referrer's eligibility and referral history have been checked.
- A referrer need not hold the same product as the account being referred. Referrer tenure is measured from the earliest Rho-Bank checking-account opening date.
- If a prerequisite is unknown, approximate, unsupported, or unverified, do not treat it as satisfied. State what must be confirmed.
- If the customer asks to take a banking action, use only the execution agent's normal banking tools. Before acting, verify identity, authority, account ownership, product eligibility, available balance or credit, fees, limits, cutoffs, recipient and card details, and confirmation requirements.

## Required workflow

1. **Identify and verify before personalized lookup.** Obtain an exact name, user ID, or email and use the corresponding read-only user lookup. Ask the customer to confirm two of the four identity fields (date of birth, email, phone number, address). After confirmation, get the current time and call `log_verification` with all required record fields. Do not repeat private lookup details in conversational text.
2. **Retrieve history before advice.** Only after identity verification, call `get_referrals_by_user` with the verified user ID. Obtain the current time for rolling-window assessment. Inspect the returned records before making any substantive policy assertion or recommendation.
3. **Collect all decision facts.** Confirm each of the following:
   - days since the referrer's earliest checking account opened and that the referrer is currently in good standing;
   - the exact amount that will be deposited, that it is a definite commitment rather than an estimate, and that it is new money rather than a Rho-Bank transfer;
   - the prospective business is new to Rho-Bank and has no existing account or account closed in the past 12 months;
   - the prospective business has a different primary owner / primary authorized signer from every existing Rho-Bank business account;
   - the prospective business has a different registered address from the referrer;
   - the prospective business will retain the qualifying deposit for at least 30 days after the qualification period ends;
   - both accounts will remain in good standing;
   - no other new-account promotion will be used and only one referral code will be used.
4. Normalize verified facts and the observed referral history to the evaluator schema and run `scripts/evaluate_referral.py`.
5. Read the evaluator result. If `ok` is false, correct missing or malformed facts. If `referrer_gate.eligible_to_receive_recommendation` is false, do not name a best program; explain the missing, failed, blocked, or timestamp-uncertain condition.
6. If recommendations are returned, lead with the first: account name, referrer bonus, qualifying new-money deposit, deposit window, and referrer-tenure requirement. State that payment remains conditional on all qualification conditions, the annual cap, and the rolling cap.

## Mandatory incomplete-information response

When the prospective LLC eligibility facts or the definite qualifying new-money deposit are unknown, begin the deferral with this exact sentence (including the contraction):

> I can't provide a confirmed account recommendation yet.

Then request the unresolved facts explicitly. The message must include the phrases or their clear equivalents: **new to Rho-Bank**, **past 12 months**, **different primary owner** (or **different primary authorized signer**), **different registered address**, **qualifying new money**, **30 days**, **good standing**, and **one referral code**. Do not call World Blue, True Blue, Beige, or any other account a confirmed, recommended, best, or qualifying choice in that response.

For example, after identity verification and history retrieval, ask whether the LLC is new to Rho-Bank with no account in the past 12 months, has a different primary owner and different registered address, and whether it will make an exact qualifying new-money deposit (not merely “around” an amount). Also ask for confirmation of 30-day retention, both accounts' good standing, no other promotion, and one referral code.

An amount described as “around,” “about,” or otherwise approximate is not a confirmed qualifying deposit. It can support a conditional comparison only after all other facts have been verified; it cannot support a confirmed recommendation until the customer commits to an exact amount at or above the relevant threshold.

## Documented program data

The evaluator compares only programs whose supplied terms document the required qualification criteria.

| Referred account | Referrer bonus | Annual cap | New-money qualifying deposit | Deposit window | Referrer tenure |
|---|---:|---:|---:|---:|---:|
| Beige | $500 | 15 | $100,000 | 120 days | 120 days |
| True Blue | $350 | 15 | $50,000 | 120 days | 90 days |
| World Blue | $300 | 12 | $25,000 | 90 days | 90 days |
| Lime Green | $200 | 12 | $15,000 | 90 days | 90 days |
| Hunter Green | $175 | 10 | $10,000 | 90 days | 60 days |
| Cobalt Blue | $150 | 10 | $7,500 | 90 days | 60 days |
| Navy Blue | $100 | 10 | $5,000 | 90 days | 60 days |

Sky Blue has a documented $150 referrer bonus and annual limit of 8, but the supplied terms do not establish a qualifying-deposit rule or a referrer-tenure requirement. It must never be returned as confirmed eligible.

The annual cap counts `COMPLETE` referrals for the target program in the calendar year of `as_of`. The universal rolling limit counts all `COMPLETE` referral bonuses across account types: at most two in any rolling nine-day window. Obtain full bonus timestamps when possible. A date-only record on the nine-day boundary is insufficient for a safe decision.

## Evaluator interface

Run the packaged script with one JSON object on standard input and read one JSON object from standard output:

```sh
printf '%s' "$REFERRAL_FACTS_JSON" | python3 scripts/evaluate_referral.py
```

Input schema:

```json
{
  "as_of": "ISO-8601 timestamp including an offset",
  "proposed_deposit": "number",
  "proposed_deposit_confirmed": "boolean",
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
      "bonus_timestamp": "ISO-8601 timestamp when available; otherwise YYYY-MM-DD"
    }
  ]
}
```

All top-level, referrer, and candidate fields are required. Referral records may use `date` instead of `bonus_timestamp`; convert runtime dates such as `MM/DD/YYYY` to `YYYY-MM-DD` before invoking the script. `proposed_deposit_confirmed` must be true before a program can be eligible. Validate `ok: true` before relying on any result.

The output contains `referrer_gate`, `rolling_window`, individual `programs`, and bonus-descending `recommendations`. Do not disclose private history contents from evaluator output; state only whether frequency and annual-cap checks passed, failed, or could not be determined.

## Response guidance

For a confirmed qualifying result, identify the highest confirmed referrer bonus, its account, required exact new-money deposit, deposit window, and tenure requirement. Do not describe a larger-bonus program as available unless its higher deposit and tenure requirements are actually confirmed. Mention the common requirements: qualifying funds must be new money; they must remain for 30 days after the qualification period; both accounts must remain in good standing; and no other new-account promotion or additional referral code may be used.
